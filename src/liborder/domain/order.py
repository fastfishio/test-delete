from typing import Union
from pydantic import Field
import itertools
import json
import logging
import random
import string
from datetime import timedelta, datetime
from decimal import Decimal
from typing import List

from jsql import sql
from noonutil.v2 import sqlutil

from libexternal import invoicing, customer
from liborder import ctx, models, domain, Context
from liborder.domain import helpers
from liborder.domain import payment
from liborder.domain import status
from liborder.domain.enums import OrderPayer, SalesOrderHistoryEventType, SessionOwnerType
from liborder.domain.enums import PaymentMethod, PREPAID_PAYMENT_METHOD_CODES
from liborder.domain.enums import Status, CancelReason
from liborder.domain.boilerplate_event import ActionCode, create_events, create_event, BoilerplateEvent
from liborder.domain.preference import DeliveryPreference, get_order_delivery_preferences
from libutil import translation
from libutil import util
from libutil.translation import _

logger = logging.getLogger(__name__)


class PlaceOrder(util.NoonBaseModel):
    total: Decimal

    def execute(self):
        # refresh is set to False so the order would be created with the same details the customer sees
        session = domain.session.GetOrCreate(refresh=False).execute()

        active_order = sql(
            ctx.conn,
            '''
            SELECT *
            FROM session_order 
            WHERE session_code = :session_code
            AND is_active = 1
            FOR UPDATE
        ''',
            session_code=session.session_code,
        ).dict()
        if active_order:
            return {'order_nr': active_order['order_nr']}
        assert session.items, "Empty cart"
        assert session, "Invalid session code"
        assert session.user_type == 'customer', "Must be logged in"
        assert session.payment_method_code, "Payment method is not set"
        assert session.address_key, "Address details missing"
        address = customer.get_customer_address(session.address_key)
        assert address, "Invalid address"
        assert address.customer_code == session.user_id, "Invalid address"
        assert address.is_phone_verified, "Phone is not verified"
        if not session.is_cod_allowed and session.payment_method_code == PaymentMethod.COD.value:
            assert False, 'Cash on Delivery is not allowed'
        if Context.is_production:
            for item in session.items:
                assert item.id_partner == 9403, "Only partner 9403 allowed during testing phase"

        # todo: explicitly create order dict instead of copying from session first
        #  so that we are clear what all is available in order?
        order = session.dict()
        # TODO: Get appropriate wh code(s) for the order
        wh_code = helpers.get_warehouses_for_country(ctx.country_code)[0]['wh_code']
        order['wh_code'] = wh_code
        order['order_nr'] = generate_order_nr(order['wh_code'], order['country_code'])
        order['status_code_order'] = Status.PENDING.value
        order['status_code_logistics'] = Status.NOT_SYNCED.value
        order['status_code_oms'] = Status.NOT_SYNCED.value
        order['status_code_payment'] = Status.PENDING.value
        order['customer_code'] = session.user_id
        order['customer_uphone_code'] = session.customer_uphone_code

        # TODO @akash: Fix hardcoded value
        order['estimated_delivery_at'] = datetime.utcnow() + timedelta(minutes=15)
        order['original_estimated_delivery_at'] = order['estimated_delivery_at']

        order['order_total'] = self.total
        order['order_credit_amount'] = -min(order['order_total'], session['credit_amount'])
        order['order_payer_code'] = OrderPayer.CUSTOMER.value
        order['order_mp_adjustment'] = 0
        order['order_credit_captured'] = 0
        order['payment_intent_token'] = None
        order['order_collect_from_customer'] = order['order_total']
        order['order_payment_amount'] = max(order['order_collect_from_customer'] + order['order_credit_amount'], 0)
        order['payment_token'] = session.payment_token

        order['initial_order_total'] = order['order_total']
        order['initial_order_subtotal'] = order['order_subtotal']
        order['initial_order_delivery_fee'] = order['order_delivery_fee']

        assert session['payment_method_code'] != PaymentMethod.NOPAYMENT.value or order['order_payment_amount'] == 0, _(
            "Invalid Payment Method"
        )
        order['subscription_id'] = None
        if order.get('payment_token'):
            order['subscription_id'] = payment.get_payment_subscription_id(order['address_key'], order['payment_token'])

        items = []
        session_order = {'session_code': session.session_code, 'order_nr': order['order_nr'], 'is_active': 1}

        sqlutil.insert_one(ctx.conn, models.tables.SessionOrder, session_order)
        id_sales_order = sqlutil.insert_one(ctx.conn, models.tables.SalesOrder, order).lastrowid
        order['id_sales_order'] = id_sales_order
        sqlutil.insert_one(ctx.conn, models.tables.OrderEtaHistory, order)

        order_delivery_prefernces = [
            {
                'id_sales_order': id_sales_order,
                'id_delivery_preference': models.util.get_id_by_code('delivery_preference', dp.code),
            }
            for dp in session.delivery_preferences
        ]
        sqlutil.insert_batch(ctx.conn, models.tables.SalesOrderDeliveryPreference, order_delivery_prefernces)

        index = 1
        for item in order['items']:
            item['id_sales_order'] = id_sales_order
            for x in range(item['qty']):
                item['item_nr'] = f"{order['order_nr']}-{index}"
                index += 1
                items.append(dict(item))

        actual_total = sum(item['qty'] * item['price'] for item in order['items']) + order['order_delivery_fee']

        assert util.equal_decimals(actual_total, self.total), "Invalid price total"
        assert util.equal_decimals(actual_total, order['order_total']), "Invalid price total"

        sqlutil.insert_batch(ctx.conn, models.tables.SalesOrderItem, items)
        domain.session.deactivate_session(SessionOwnerType.CUSTOMER, ctx.customer_code)
        if order['payment_method_code'] in PREPAID_PAYMENT_METHOD_CODES or order['order_credit_amount']:
            create_event(ActionCode.PAYMENT_ORDER_CREATE, {'order_nr': order['order_nr']})
            postcommit_create_paymentintent_in_bg_thread(order['order_nr'])
        else:
            status.PaymentStatus(order['order_nr']).transition(Status.DONE.value)
        return {'order_nr': order['order_nr']}


class GetDetails(util.NoonBaseModel):
    order_nr: str

    def execute(self, internal=False, formatted=True, local_tz=False, lock=False):

        if not internal:
            assert ctx.customer_code, "Customer not logged in"

        items = sql(
            ctx.conn,
            '''
            SELECT
                id_sales_order,
                order_nr,
                customer_code,
                payment_method_code,
                credit_card_bin,
                credit_card_mask,
                subscription_id,
                c.currency_code,
                address_key,
                wh_code,
                country_code,
                initial_order_subtotal,
                initial_order_delivery_fee,
                initial_order_total,
                order_subtotal,
                order_delivery_fee,
                order_payer_code,
                order_payment_amount,
                order_payment_captured,
                order_payment_authorized,
                order_payment_refunded,
                order_payment_cash_collected,
                order_issued_credit,
                order_issued_credit_captured,
                order_collect_from_customer,
                order_collected_from_customer,
                payment_intent_token,
                payment_token,
                order_total,
                order_credit_amount,
                order_credit_captured,
                order_mp_adjustment,
                {% if not local_tz %}
                    estimated_delivery_at,
                    original_estimated_delivery_at,
                    canceled_at,
                    placed_at,
                    delivered_at
                {% else %}
                    CONVERT_TZ(estimated_delivery_at ,'UTC', c.time_zone) as estimated_delivery_at,
                    CONVERT_TZ(original_estimated_delivery_at ,'UTC', c.time_zone) as original_estimated_delivery_at,
                    CONVERT_TZ(canceled_at ,'UTC', c.time_zone) as canceled_at,
                    CONVERT_TZ(placed_at ,'UTC', c.time_zone) as placed_at,
                    CONVERT_TZ(delivered_at ,'UTC', c.time_zone) as delivered_at,
                {% endif %}
                order_collect_from_customer,
                order_payment_authorized,
                order_payment_captured,
                order_mp_adjustment,
                order_credit_captured,
                status_code_order,
                status_code_payment,
                status_code_oms,
                status_code_logistics,
                invoice_nr,
                id_sales_order_item,
                item_nr,
                id_partner,
                sku,
                price,
                cancel_reason_code
            FROM sales_order o
            LEFT JOIN sales_order_item i USING(id_sales_order)
            LEFT JOIN country c using(country_code)
            WHERE order_nr = :order_nr
            {% if not internal %} AND customer_code = :customer_code {% endif %}
            {% if lock %} FOR UPDATE {% endif %}
        ''',
            order_nr=self.order_nr,
            customer_code=ctx.customer_code,
            internal=internal,
            local_tz=local_tz,
            lock=lock,
        ).dicts()

        assert items, "no order found"

        order = items[0].copy()

        order['is_invoice_ready'] = bool(order['invoice_nr'])

        if order['credit_card_mask']:
            order['credit_card_type'] = util.get_credit_card_type(cc_mask=order['credit_card_mask'])

        skus = [(item['sku'], item['wh_code']) for item in items]
        enriched_offers = helpers.enrich_offers(skus)
        for item in items:
            enriched_item = enriched_offers[(item['sku'], item['wh_code'])]
            enrich_fields = [
                'image_key',
                'title',
                'brand',
                'title_ar',
                'brand_ar',
                'title_en',
                'brand_en',
                'id_product_fulltype',
            ]
            item['cancel_reason'] = None
            if item['cancel_reason_code']:
                cancel_reason_map = helpers.get_cancel_reason_map(internal=0, item_level=1)
                # This doesn't feel right, but not sure how to do it otherwise,
                # since CS cancellation reason is internal, we shouldn't show it to customers,
                # but we still want to store it in DB
                if item['cancel_reason_code'] not in cancel_reason_map:
                    #  Cancel reason is by CS
                    item['cancel_reason'] = cancel_reason_map[CancelReason.CS_CANCELATION.value][f'name_{ctx.lang}']
                else:
                    item['cancel_reason'] = cancel_reason_map[item['cancel_reason_code']][f'name_{ctx.lang}']
            for field in enrich_fields:
                item[field] = enriched_item[field]

        order['items'] = items
        order.update(domain.payment.get_invoice_info(order))

        return format_order(order, internal=internal) if formatted else order


class ListOrders(util.NoonBaseModel):
    orders_per_page: int = 20
    page_nr: int = Field()

    def execute(self):
        assert self.orders_per_page > 0, "Invalid orders per page"
        assert self.page_nr > 0, "Invalid page number"
        self.orders_per_page = min(self.orders_per_page, 25)

        offset = self.orders_per_page * (self.page_nr - 1)
        limit = self.orders_per_page
        total_orders = sql(
            ctx.conn,
            '''
            SELECT COUNT(*)
            FROM sales_order
            WHERE customer_code = :customer_code
        ''',
            customer_code=ctx.customer_code,
        ).scalar()
        total_pages = total_orders // self.orders_per_page + (1 if total_orders % self.orders_per_page else 0)
        order_nrs = sql(
            ctx.conn,
            '''
            SELECT order_nr
            FROM sales_order
            WHERE customer_code = :customer_code
            ORDER BY created_at DESC
            LIMIT :limit
            OFFSET :offset
        ''',
            customer_code=ctx.customer_code,
            limit=limit,
            offset=offset,
        ).scalars()
        order_items = []
        if order_nrs:
            order_items = sql(
                ctx.conn,
                '''
                SELECT *
                FROM sales_order o
                LEFT JOIN sales_order_item i USING(id_sales_order)
                LEFT JOIN country USING(country_code)
                WHERE order_nr IN :order_nrs_list
                ORDER BY o.created_at DESC
            ''',
                order_nrs_list=order_nrs,
            ).dicts()
        skus = [(item['sku'], item['wh_code']) for item in order_items]
        enriched_offers = helpers.enrich_offers(skus)

        orders = []
        order_map = {}
        for item in order_items:
            if item['order_nr'] in order_map:
                orders[-1].append(item)
            else:
                orders.append([item])
                order_map[item['order_nr']] = 1
        final_orders = []
        for order in orders:
            for item in order:
                enriched_item = enriched_offers[(item['sku'], item['wh_code'])]
                enrich_fields = ['image_key', 'title', 'brand', 'title_ar', 'brand_ar', 'title_en', 'brand_en']
                for field in enrich_fields:
                    item[field] = enriched_item[field]
            final_order = order[0].copy()
            final_order['items'] = order
            final_orders.append(format_order(final_order, summary=True))
        return OrderList(total_pages=total_pages, orders=final_orders)


# Without items as we don't have a use case for that currently
class ManyOrders(util.NoonBaseModel):
    order_nrs: List[str]

    def execute(self, with_customer_info=False, local_tz=False, sort_key=None):
        orders = sql(
            ctx.conn,
            '''
            SELECT
                id_sales_order,
                order_nr,
                customer_code,
                payment_method_code,
                subscription_id,
                c.currency_code,
                address_key,
                wh_code,
                country_code,
                order_subtotal,
                order_delivery_fee,
                order_payer_code,
                order_payment_amount,
                payment_intent_token,
                order_total,
                {% if not local_tz %}
                    estimated_delivery_at,
                    original_estimated_delivery_at,
                    placed_at,
                    delivered_at
                {% else %}
                    CONVERT_TZ(estimated_delivery_at ,'UTC', c.time_zone) as estimated_delivery_at,
                    CONVERT_TZ(original_estimated_delivery_at ,'UTC', c.time_zone) as original_estimated_delivery_at,
                    CONVERT_TZ(placed_at ,'UTC', c.time_zone) as placed_at,
                    CONVERT_TZ(delivered_at ,'UTC', c.time_zone) as delivered_at,
                {% endif %}
                order_collect_from_customer,
                order_issued_credit,
                order_payment_authorized,
                order_payment_captured,
                order_mp_adjustment,
                order_credit_captured,
                status_code_order,
                status_code_payment,
                status_code_oms,
                status_code_logistics,
                invoice_nr
            FROM sales_order o
            LEFT JOIN country c using(country_code)
            WHERE order_nr IN :order_nrs_list
            {% if sort_key %} ORDER BY o.{{sort_key}} DESC {% endif %}
        ''',
            order_nrs_list=self.order_nrs,
            local_tz=local_tz,
            sort_key=sort_key,
        ).dicts()
        if with_customer_info:
            address_map = {}
            uq_addresses = list(set([order['address_key'] for order in orders]))
            address_details = customer.get_customer_info_bulk(uq_addresses)
            for address in address_details:
                address_map[address['address_key']] = address
            for order in orders:
                address = address_map.get(order['address_key'])
                order['customer_name'] = address['name']
                order['status'] = order['status_code_order']
                order['customer_phone'] = address['phone']
                order['customer_street_address'] = address['street_address']
        return orders


def cancel_order(order_nr, reason_code=CancelReason.CUSTOMER_CANCELATION.value):
    order_details = GetDetails(order_nr=order_nr).execute(internal=True)
    #  should we cancel oms and logistics order/tasks first?
    #  should we do it via events or direct API calls?
    # what if order status is cancelled
    # but oms/logistics status is not cancelled
    #  need to work through these cases
    assert (
        order_details.status_code not in status.ORDER_TERMINAL_STATES
        and order_details.status_code_oms != Status.SHIPPED.value
    ), 'cannot cancel the order now. it is already shipped'

    items_to_update = []
    for item in order_details.items:
        item.canceled_at = datetime.utcnow()
        item.cancel_reason_code = reason_code
        item.id_sales_order = order_details.id_sales_order
        items_to_update.append(item.__dict__)

    sqlutil.upsert(
        ctx.conn,
        models.tables.SalesOrderItem,
        order_details['items'],
        unique_columns=['item_nr'],
        update_columns=['cancel_reason_code', 'canceled_at'],
    )

    modify_order(
        order_nr,
        {'order_payer_code': OrderPayer.NONE.value, 'status_code_order': Status.CANCELLED.value},
        internal=True,
    )

    # not sure if the below should be here (or rather, should we schedule it at a later time)
    create_events(
        [
            BoilerplateEvent(action_code=ActionCode.SETTLE_PAYMENT, data={'order_nr': order_nr}),
            BoilerplateEvent(action_code=ActionCode.NOTIFICATION_ORDER_UPDATE, data={'order_nr': order_nr}),
        ]
    )


class GetInvoice(util.NoonBaseModel):
    order_nr: str

    def execute(self):
        order = GetDetails(order_nr=self.order_nr).execute()

        assert order, 'Order not found'
        assert order.is_invoice_ready, 'Invoice not ready'

        url = invoicing.get_invoice_url_for(order.order_nr)
        return {'url': url}


def validate_payment_method(payment_method_code):
    return payment_method_code == 'postpaid'


def generate_order_nr(wh_code, country_code):
    random_digits = ''.join(random.choices(string.digits + string.ascii_lowercase, k=8))
    wh_code_encoded = util.get_digest(wh_code)[-3:]
    date_encoded = util.encode_date()
    tail = 'A' if Context.is_production else 'S'

    return f"I{country_code.upper()}{date_encoded}{wh_code_encoded}{random_digits}{tail}".upper()


# To merge order items based on sku for order listing
# and based on (sku, status) for order details
def group_items(items, keys):
    grouped_items_map = {}
    group_key_to_item_map = {}
    for item in items:
        group_key = tuple([item[key] for key in keys])
        group_key_to_item_map[group_key] = item
        if group_key in grouped_items_map:
            grouped_items_map[group_key] += 1
        else:
            grouped_items_map[group_key] = 1
    grouped_items = []
    for group_key in grouped_items_map.keys():
        item = group_key_to_item_map[group_key]
        item['qty'] = grouped_items_map[group_key]
        grouped_items.append(item)
    return grouped_items


def is_cancelable(order: dict):
    status_code = order['status_code']
    return status_code not in status.ORDER_TERMINAL_STATES and not order["status_code_oms"] == Status.SHIPPED.value


def format_order(order, summary=False, internal=False):
    order['status_code'] = order["status_code_order"]
    if order['status_code'] in [Status.CANCELLED.value or Status.UNDELIVERED.value]:
        order['status_color'] = '#E84442'
    elif order['status_code'] == Status.DELIVERED.value:
        order['status_color'] = '#38AE04'
    else:
        order['status_color'] = '#7E859B'
    order['status'] = helpers.get_status_map()[order['status_code']][f'name_{ctx.lang}']
    order['placed_on_text'] = None
    if order['status_code'] == Status.DELIVERED.value and order.get('placed_at'):
        order['placed_on_text'] = f'{_("Placed on")} {util.format_date(order["placed_at"])}'
    is_cod = order['payment_method_code'] == PaymentMethod.COD.value
    order['delivery_preferences'] = get_order_delivery_preferences(order['order_nr'], is_cod)
    for i in order['items']:
        i['id_sales_order'] = order['id_sales_order']
        i['status_code'] = Status.CANCELLED.value if i['cancel_reason_code'] else Status.CONFIRMED.value
        i['status'] = helpers.get_status_map()[i['status_code']][f'name_{ctx.lang}']
    order['order_summary'] = get_order_summary(order)
    order['is_cancelable'] = is_cancelable(order)
    if not summary:
        if internal:
            return OrderDetailsInternal(**order)
        order['item_sections'] = format_items_by_status(order)
        return OrderDetails(**order)
    order['items'] = group_items(order['items'], ['sku'])
    return OrderSummary(**order)

def format_items_by_status(order):
    order['items'] = group_items(order['items'], ['sku', 'status_code'])
    status_to_items_map = {}
    possible_statuses = [
        Status.CONFIRMED.value,
        Status.DELIVERED.value,
        Status.CANCELLED.value,
        Status.UNDELIVERED.value,
    ]
    for item in order['items']:
        assert item['status_code'] in possible_statuses
        if item['status_code'] not in status_to_items_map:
            status_to_items_map[item['status_code']] = [item]
        else:
            status_to_items_map[item['status_code']].append(item)
    sections = []
    for status in possible_statuses:
        if status not in status_to_items_map:
            continue
        section = []
        is_oos_cancellation = False
        for item in status_to_items_map[status]:
            if status in [Status.CONFIRMED.value, Status.DELIVERED.value]:
                item['price_text'] = f"<b>{order['currency_code']}</b> {util.decimal_round(item['price'])}"
            if item['cancel_reason']:
                item['subtitle'] = item['cancel_reason']
            # if any of the item has OOS cancelation reason, show the tooltip
            if not is_oos_cancellation and item['cancel_reason_code'] == domain.enums.CancelReason.OUT_OF_STOCK.value:
                is_oos_cancellation = True
            section.append(ItemDescription(**item))
        if section:
            item_text = _('items') if len(section) > 1 else _('item')
            title = f"{helpers.get_status_map()[status][f'name_{ctx.lang}']} ({len(section)} {item_text})"
            tool_tip = None
            if is_oos_cancellation:
                tool_tip = get_tool_tip(order, reason='oos')
            sections.append(OrderItemSection(title=title, tool_tip=tool_tip, items=section))
    return sections


def modify_order(order_nr, modifier, internal=False, order=None, trigger_payment_update=True):
    assert callable(modifier) or isinstance(modifier, dict), 'modifier can either be a function or dict'
    order = GetDetails(order_nr=order_nr).execute(internal=internal, formatted=False, lock=True)

    delivery_estimates = ['estimated_delivery_at']

    prev_estimates = [order[estimate] for estimate in delivery_estimates]
    prev_order_status = order['status_code_order']

    to_modify = modifier
    if callable(modifier):
        to_modify = modifier(order)

    # update order dict with whatever is returned by the function
    order.update(to_modify)

    #  since we don't want to update all columns because of concurrency issues
    #   we maintain the list of columns to update
    columns_to_update = list(to_modify.keys())
    cur_estimates = [order[estimate] for estimate in delivery_estimates]
    order["status_code_order"] = get_order_status(order)
    cur_order_status = order['status_code_order']

    if prev_estimates != cur_estimates:
        sqlutil.insert_one(ctx.conn, models.tables.OrderEtaHistory, order)

    order_event = {
        'id_sales_order': order['id_sales_order'],
        'event_type': SalesOrderHistoryEventType.ORDER_STATUS.value,
        'time': datetime.utcnow(),
        'value': order['status_code_order'],
    }
    logistics_event = {
        'id_sales_order': order['id_sales_order'],
        'event_type': SalesOrderHistoryEventType.LOGISTICS.value,
        'time': datetime.utcnow(),
        'value': order['status_code_logistics'],
    }
    sqlutil.insert_one(ctx.conn, models.tables.SalesOrderHistoryEvent, order_event, ignore=True)
    sqlutil.insert_one(ctx.conn, models.tables.SalesOrderHistoryEvent, logistics_event, ignore=True)

    if cur_order_status != prev_order_status:
        if cur_order_status == Status.DELIVERED.value:
            create_event(
                ActionCode.GENERATE_INVOICE,
                data={'order_nr': order_nr},
                schedule_at=datetime.utcnow() + timedelta(hours=24),
            )

    order["order_payer_code"] = get_order_payer_code(order)
    invoice_dict = domain.payment.get_invoice_info(order)
    order.update(invoice_dict)

    columns_to_update += invoice_dict.keys()
    columns_to_update += ['order_payer_code', 'status_code_order']

    columns_to_update = set(columns_to_update) & set(models.tables.SalesOrder.__table__.columns.keys())
    sqlutil.upsert(
        ctx.conn, models.tables.SalesOrder, [order], unique_columns=['order_nr'], update_columns=columns_to_update
    )
    if trigger_payment_update:
        domain.payment.after_payment_related_update(order_nr)
    return format_order(order, internal=internal)


#  this fn is a WIP, logic is also duplicated in get_order_status()
# """
# The goal of this function is to update status_code_order based on logistics_status and oms_status
# so this should be called everytime when logistics or oms status changes for an order
# """

# too many db calls to GetDetails - can be optimized


def reactivate(order: dict, session_code):
    active_session_items = sql(
        ctx.conn,
        '''
        SELECT id_session_item FROM session
        LEFT JOIN session_item USING(id_session)
        WHERE user_type = 'customer'
        AND user_id = :customer_code
        AND is_active = 1
        AND country_code = :country_code
    ''',
        customer_code=order['customer_code'],
        country_code=ctx.country_code,
    ).scalars()
    if active_session_items and active_session_items[0]:
        # new session has items, don't activate old session
        return
    else:
        # Deactivate the new session and activate the old one for which the payment failed/was canceled to restore cart
        domain.session.deactivate_session(SessionOwnerType.CUSTOMER, order['customer_code'])
        domain.session.activate_session(session_code)
        sql(
            ctx.conn,
            '''
            UPDATE session_order
            SET is_active = NULL
            WHERE order_nr = :order_nr
        ''',
            order_nr=order['order_nr'],
        )


def reactivate_order_session(order_nr):
    logger.info(f"reactivating session for {order_nr}")
    session_code = sql(
        ctx.conn,
        '''
        SELECT session_code
        FROM session_order
        WHERE order_nr = :order_nr
        AND is_active = 1
    ''',
        order_nr=order_nr,
    ).scalar()
    order = GetDetails(order_nr=order_nr).execute(internal=True, formatted=False)
    if not session_code:
        # Should this case ever happen?
        return
    reactivate(order, session_code)


# revisit this, lot of cases
def get_order_status(order: dict):
    status_code = order['status_code_order']
    if status_code in status.ORDER_TERMINAL_STATES:
        return status_code
    if order['status_code_payment'] in {Status.PENDING.value, Status.CANCELLED.value, Status.FAILED.value}:
        status_code = order['status_code_payment']
    elif order['status_code_logistics'] in {
        Status.ARRIVED_AT_PICKUP.value,
        Status.PICKED_UP.value,
        Status.ARRIVED_AT_DELIVERY.value,
        Status.DELIVERED.value,
        Status.UNDELIVERED.value,
        Status.CANCELLED.value,
    }:
        status_code = order['status_code_logistics']
    elif order['status_code_oms'] in {Status.SHIPPED.value}:
        status_code = Status.READY_FOR_PICKUP.value
    elif order['status_code_payment'] in {Status.DONE.value}:
        status_code = Status.CONFIRMED.value
    return status_code


def get_order_payer_code(order: dict):
    if order['status_code_logistics'] in {Status.UNDELIVERED.value, Status.CANCELLED.value}:
        return OrderPayer.NONE.value
    if order['status_code_order'] in {Status.CANCELLED.value, Status.FAILED.value}:
        return OrderPayer.NONE.value
    return OrderPayer.CUSTOMER.value


def get_shipments_for(order_nr):
    rows = sql(
        ctx.conn,
        '''
        SELECT awb_nr, item_nr
        FROM shipment
        LEFT JOIN shipment_item USING(id_shipment)
        WHERE order_nr = :order_nr
    ''',
        order_nr=order_nr,
    ).dicts()
    shipments = {row['awb_nr']: [] for row in rows}
    for row in rows:
        shipments[row['awb_nr']].append(row['item_nr'])
    return shipments


def add_shipment(shipment, items):
    with Context.service():
        sqlutil.upsert_one(ctx.conn, models.tables.Shipment, shipment)
        id_shipment = sql(
            ctx.conn,
            '''
            SELECT id_shipment
            FROM shipment
            WHERE awb_nr = :awb_nr 
        ''',
            awb_nr=shipment['awb_nr'],
        ).scalar()
        for item in items:
            item['id_shipment'] = id_shipment
        sqlutil.upsert(
            ctx.conn,
            models.tables.ShipmentItem,
            items,
            unique_columns=['id_shipment', 'item_nr'],
            insert_columns=['id_shipment', 'item_nr'],
        )
        return create_event(ActionCode.ORDER_SHIPMENT_CREATED, {'order_nr': shipment['order_nr']})


# todo: simplify this a bit
'''
The goal of the function should only be to mark items not received in shipment as canceled
and send updates to logistics about the status change
'''


def order_ready_for_pickup(event):
    order_nr = event['data']['order_nr']
    order_details = GetDetails(order_nr=order_nr).execute(internal=True)
    shipments = get_shipments_for(order_nr=order_nr)
    order_items = set([item.item_nr for item in order_details.items if item.status_code != Status.CANCELLED.value])
    shipment_items = set(itertools.chain.from_iterable(shipments.values()))
    canceled_items = order_items - shipment_items
    items_to_update = []
    for item in order_details.items:
        if item.item_nr in canceled_items:
            item.canceled_at = datetime.utcnow()
            item.cancel_reason_code = CancelReason.OUT_OF_STOCK.value
            items_to_update.append(item.__dict__)

    sqlutil.upsert(
        ctx.conn,
        models.tables.SalesOrderItem,
        items_to_update,
        unique_columns=['item_nr'],
        update_columns=['cancel_reason_code', 'canceled_at'],
    )

    #  nothing to update in sales_order from here, but need to call modify order to update other fields
    modify_order(order_nr, {}, internal=True)
    # here, since some items might have been cancelled, we need to update
    #  collect_from_customer etc, hence calling after_payment_related_update
    create_event(ActionCode.LOGISTICS_ORDER_UPDATE, {'order_nr': order_nr})

    if order_details.payment_method_code in PREPAID_PAYMENT_METHOD_CODES:
        create_event(ActionCode.PAYMENT_ORDER_CAPTURE, {'order_nr': order_nr})

    if canceled_items:
        create_event(ActionCode.NOTIFICATION_ORDER_UPDATE, {'order_nr': order_nr, 'info': 'partial_shipment'})


# what is the difference between shipment created and ready for pickup
#  can we assume that once shipment is created, order is ready for pickup?
def order_shipment_created(event):
    # todo: change this into modify_order way
    order_nr = event['data']['order_nr']
    shipments = get_shipments_for(order_nr=order_nr)
    shipment_items = set(itertools.chain.from_iterable(shipments.values()))

    if shipment_items:
        modify_order(order_nr, {'status_code_oms': Status.SHIPPED.value}, internal=True)
        create_event(ActionCode.ORDER_READY_FOR_PICKUP, {'order_nr': order_nr})


def order_cancel_authorized():
    order_nr_list = sql(
        ctx.conn,
        '''
            SELECT order_nr
            FROM sales_order
            WHERE payment_method_code IN :prepaid_payment_method_codes_list
            AND order_payer_code = :none_payer
            AND order_payment_authorized > 0
            AND order_payment_captured = 0
            AND created_at > UTC_TIMESTAMP - INTERVAL :hrs HOUR
        ''',
        prepaid_payment_method_codes_list=PREPAID_PAYMENT_METHOD_CODES,
        none_payer=OrderPayer.NONE.value,
        hrs=24,
    ).scalars()
    for order_nr in order_nr_list:
        logger.info(f"attempting to reverse payment for order_nr: {order_nr}")
        domain.payment.payment_capture(order_nr, 0)


def cancel_order_with_no_shipments(event):
    order_nr = event['data']['order_nr']
    shipments = get_shipments_for(order_nr=order_nr)
    if shipments:
        return

    order_details = GetDetails(order_nr=order_nr).execute(internal=True)

    if order_details.status_code == Status.CANCELLED.value:
        return

    order_items = set([item.item_nr for item in order_details.items if item.status_code != Status.CANCELLED.value])

    items_to_update = []
    for item in order_details.items:
        if item.item_nr in order_items:
            item.canceled_at = datetime.utcnow()
            item.cancel_reason_code = CancelReason.OUT_OF_STOCK.value
            items_to_update.append(item.__dict__)

    sqlutil.upsert(
        ctx.conn,
        models.tables.SalesOrderItem,
        items_to_update,
        unique_columns=['item_nr'],
        update_columns=['cancel_reason_code', 'canceled_at'],
    )

    modify_order(order_nr, {'status_code_order': Status.CANCELLED.value}, internal=True)

    create_event(ActionCode.NOTIFICATION_ORDER_UPDATE, {'order_nr': order_nr})


# the below is optional so that we create the payment intent immediately
#  without waiting for the worker to process PAYMENT_ORDER_CREATE event
def postcommit_create_paymentintent_in_bg_thread(order_nr):
    if Context.is_testing:
        return

    def helper():
        with Context.service():
            logger.info(f"payment order create in bg thread: {order_nr}")
            payment.payment_order_create({"data": {"order_nr": order_nr}})

    def submit_to_executor():
        util.threadpool.submit(helper)

    # schedule creation to happen only if and after the DB tx is committed
    ctx.register_postcommit('create-payment-intent', submit_to_executor)


# def update_task_details(task):
#     def modify_order_fn(modified_order):
#         to_update = {}
#         current_status = modified_order['status_code_logistics']
#         if current_status != Status.DELIVERED.value and task['status_code'] == Status.DELIVERED.value:
#             modified_order['delivered_at'] = datetime.utcnow()
#         if current_status in domain.status.LOGISTICS_TERMINAL_STATES:
#             logger.warning(f"order {task['mp_task_nr']} already in terminal state. ignoring update")
#             return to_update
#         to_update['status_code_logistics'] = task['status_code']

#         if task.get('status_history'):
#             logistics_history = {}
#             status_history = task['status_history']
#             for status_dict in status_history:
#                 logistics_history[status_dict['status_code']] = int(
#                     datetime.strptime(status_dict['updated_at'], '%Y-%m-%dT%H:%M:%S').timestamp()
#                 )
#             to_update['logistics_status_history'] = json.dumps(logistics_history)

#         # TODO: handle logistic terminal state
#         # To prevent customer addresses from appearing in BQ (sensitive info)
#         # if logistics.is_terminal_state(task['status_code']):
#         #     cash_collected = util.from_cent(task['order_cash_collected']) if task['order_cash_collected'] else None
#         #     if cash_collected:
#         #         logger.info(
#         #             f"setting cash collected in modify_order fn for order: {task['mp_task_nr']} -- {cash_collected}")
#         #         to_update['order_payment_cash_collected'] = cash_collected
#         #
#         #     create_event(ActionCode.SETTLE_PAYMENT, {'order_nr': task['mp_task_nr']})
#         return to_update

#     with Context.service():
#         modify_order(order_nr=task['mp_task_nr'], modifier=modify_order_fn, internal=True)
#         create_event(
#             ActionCode.NOTIFICATION_ORDER_UPDATE, {'order_nr': task['mp_task_nr']}
#         )  # OUT_FOR_DELIVERY, DELIVERED, UNDELIVERED?


def update_default_payment_method(event):
    payment_details = event['data']
    payment_details['is_active'] = 1
    sqlutil.upsert_one(ctx.conn, models.tables.CustomerDefaultPayment, payment_details)


def eta_order_update(order):

    items_count = len(order['items'])
    est_ft = 1.5 + items_count * 0.3  # new fulfillment time estimation

    if est_ft <= 2:  # if it didn't change, no need to update anything
        return

    def update_fn(order):
        to_update = {}

        # TODO @akash: Fix hardcoded value
        to_update['estimated_delivery_at'] = datetime.utcnow() + timedelta(minutes=15)
        to_update['original_estimated_delivery_at'] = to_update['estimated_delivery_at']

        return to_update

    modify_order(order['order_nr'], update_fn, internal=True, trigger_payment_update=False)


def get_tool_tip(order: dict, reason="oos"):
    if reason != "oos":
        return
    title = _("Sorry, we had to cancel some items since they went out of stock")
    description = _("You would not be charged for these items.")
    delivery_fee_msg = ""
    delivery_fee = order["initial_order_delivery_fee"]
    currency_code = order["currency_code"]
    if delivery_fee > 0:
        delivery_fee_msg = _("We would be waving the delivery fee of %s %s because of the inconvenience") % (
            currency_code,
            delivery_fee,
        )

    description = translation.combine(description, delivery_fee_msg)
    return ToolTip(title=title, description=description)


class Item(util.NoonBaseModel):
    id_sales_order: int
    sku: str
    item_nr: str
    id_partner: int
    price: Decimal
    image_key: str = None
    title: str = None
    brand: str = None
    title_ar: str = None
    title_en: str = None
    brand_ar: str = None
    brand_en: str = None
    status_code: str
    status: str
    cancel_reason: str = None
    cancel_reason_code: str = None
    canceled_at: datetime = None


class SkuGroupedItem(util.NoonBaseModel):
    sku: str
    id_partner: int
    price: Decimal
    qty: int
    image_key: str = None
    title: str = None
    brand: str = None
    title_ar: str = None
    title_en: str = None
    brand_ar: str = None
    brand_en: str = None
    cancel_reason: str = None


class StatusGroupedItem(util.NoonBaseModel):
    sku: str
    id_partner: int
    price: Decimal
    qty: int
    image_key: str = None
    title: str = None
    brand: str = None
    title_ar: str = None
    title_en: str = None
    brand_ar: str = None
    brand_en: str = None
    status_code: str
    status: str
    cancel_reason: str = None


class OrderSummaryEntry(util.NoonBaseModel):
    title: str
    value: str


class OrderSummarySection(util.NoonBaseModel):
    entries: List[OrderSummaryEntry]


class ItemDescription(util.NoonBaseModel):
    sku: str
    price_text: str = None
    qty: int
    image_key: str = None
    title: str = None
    brand: str = None
    subtitle: str = None


class ToolTip(util.NoonBaseModel):
    title: str = None
    description: str = None


class OrderItemSection(util.NoonBaseModel):
    title: str
    tool_tip: ToolTip = None
    items: List[ItemDescription]


class CanceledItemsPopUp(util.NoonBaseModel):
    title: str
    message: str


class OrderDetails(util.NoonBaseModel):
    order_nr: str
    wh_code: str
    country_code: str
    order_subtotal: Decimal
    order_delivery_fee: Decimal
    order_credit_captured: Decimal = 0
    order_total: Decimal
    order_payment_amount: Decimal
    currency_code: str
    initial_order_subtotal: Decimal
    initial_order_delivery_fee: Decimal
    initial_order_total: Decimal
    address_key: str
    payment_method_code: str
    credit_card_mask: str = None
    credit_card_bin: str = None
    credit_card_type: str = None
    payment_intent_token: str = None
    items: List[StatusGroupedItem]
    status_code: str
    status_color: str
    status: str
    estimated_delivery_at: datetime
    estimated_delivery_text: str = None
    delivery_preferences: List[DeliveryPreference]
    placed_at: datetime
    placed_on_text: str = None
    delivered_at: datetime = None
    item_sections: List[OrderItemSection]
    order_summary: List[OrderSummarySection]
    is_invoice_ready: bool


class OrderDetailsInternal(util.NoonBaseModel):
    order_nr: str
    id_sales_order: int
    wh_code: str
    country_code: str
    currency_code: str
    customer_code: str
    subscription_id: str = None
    initial_order_subtotal: Decimal
    initial_order_delivery_fee: Decimal
    initial_order_total: Decimal
    order_subtotal: Decimal
    order_delivery_fee: Decimal
    order_credit_captured: Decimal = 0
    order_credit_amount: Decimal
    order_total: Decimal
    order_payment_amount: Decimal
    order_payment_cash_amount: Decimal
    order_payment_authorized: Decimal
    order_payment_captured: Decimal
    order_payment_refunded: Decimal
    order_payment_cash_collected: Decimal
    order_collect_from_customer: Decimal
    order_collected_from_customer: Decimal
    order_issued_credit: Decimal
    order_issued_credit_captured: Decimal
    order_payer_code: str
    order_mp_adjustment: Decimal
    payment_intent_token: str = None
    payment_token: str = None
    credit_card_mask: str = None
    address_key: str
    payment_method_code: str
    items: List[Item]
    status_code: str
    status: str
    status_code_payment: str
    status_code_logistics: str
    status_code_oms: str
    estimated_delivery_at: datetime
    delivery_preferences: List[DeliveryPreference]
    is_cancelable: bool = False
    placed_at: datetime
    delivered_at: datetime = None


class OrderSummary(util.NoonBaseModel):
    order_nr: str
    wh_code: str
    country_code: str
    order_subtotal: Decimal
    order_delivery_fee: Decimal
    currency_code: str
    order_total: Decimal
    items: List[SkuGroupedItem]
    address_key: str
    status_code: str
    status_color: str = None
    status: str
    placed_at: datetime
    placed_on_text: str = None
    delivered_at: datetime = None
    order_summary: List[OrderSummarySection]


class OrderList(util.NoonBaseModel):
    orders: List[OrderSummary]
    total_pages: int


class TestOrderItem(util.NoonBaseModel):
    sku: str
    qty: int = 1
    canceled_qty: int = 0


class TestOrder(util.NoonBaseModel):
    items: List[TestOrderItem]
    total: Decimal
    address_key: str
    payment_method_code: str = "postpaid"
    payment_toke_code: str = "4500000405"
    credit_card_mask: str = "520000xxxxxx1005"
    credit_card_bin: str = "520000"
    final_status = 'confirmed'


def get_order_summary(order):
    num_items = len(order['items'])
    if not num_items:
        return []
    item_text = f'{_("Subtotal")} ({num_items} {_("Items") if num_items > 1 else _("Item")})'
    balance = order['order_total'] + order['order_credit_captured']
    delivery_fee_text = str(util.decimal_round(order["order_delivery_fee"], replace_zero=True))
    if delivery_fee_text != 'FREE':
        delivery_fee_text = f'{order["currency_code"]} {delivery_fee_text}'
    sections = []
    section1 = [
        OrderSummaryEntry(
            title=item_text, value=f'{order["currency_code"]} {util.decimal_round(order["order_subtotal"])}'
        ),
        OrderSummaryEntry(title=_('Shipping'), value=delivery_fee_text),
    ]
    sections.append(OrderSummarySection(entries=section1))
    if order["order_credit_captured"] < 0:
        sections += [
            OrderSummarySection(
                entries=[
                    OrderSummaryEntry(
                        title=f'<b>{_("Cart total")}</b>',
                        value=f'<b>{order["currency_code"]} {util.decimal_round(order["order_total"])}</b>',
                    ),
                    OrderSummaryEntry(
                        title=_('Noon credits'),
                        value=f'- {order["currency_code"]} {-util.decimal_round(order["order_credit_captured"])}',
                    ),
                ]
            ),
            OrderSummarySection(
                entries=[
                    OrderSummaryEntry(
                        title=f'<b>{_("Balance")}</b>',
                        value=f'<b>{order["currency_code"]} {util.decimal_round(balance)}</b>',
                    )
                ]
            ),
        ]
    else:
        sections.append(
            OrderSummarySection(
                entries=[
                    OrderSummaryEntry(
                        title=f'<b>{_("Cart total")}</b>',
                        value=f'<b>{order["currency_code"]} {util.decimal_round(order["order_total"])}</b>',
                    )
                ]
            )
        )
    return sections


def format_order(order, summary=False, internal=False) -> Union[OrderDetails, OrderDetailsInternal, OrderSummary]:
    order['status_code'] = order["status_code_order"]
    if order['status_code'] in [Status.CANCELLED.value or Status.UNDELIVERED.value]:
        order['status_color'] = '#E84442'
    elif order['status_code'] == Status.DELIVERED.value:
        order['status_color'] = '#38AE04'
    else:
        order['status_color'] = '#7E859B'
    order['status'] = helpers.get_status_map()[order['status_code']][f'name_{ctx.lang}']
    order['placed_on_text'] = None
    if order['status_code'] == Status.DELIVERED.value and order.get('placed_at'):
        order['placed_on_text'] = f'{_("Placed on")} {util.format_date(order["placed_at"])}'
    is_cod = order['payment_method_code'] == PaymentMethod.COD.value
    order['delivery_preferences'] = get_order_delivery_preferences(order['order_nr'], is_cod)
    for i in order['items']:
        i['id_sales_order'] = order['id_sales_order']
        i['status_code'] = Status.CANCELLED.value if i['cancel_reason_code'] else Status.CONFIRMED.value
        i['status'] = helpers.get_status_map()[i['status_code']][f'name_{ctx.lang}']
    order['order_summary'] = get_order_summary(order)
    order['is_cancelable'] = is_cancelable(order)
    if not summary:
        if internal:
            return OrderDetailsInternal(**order)
        order['item_sections'] = format_items_by_status(order)
        return OrderDetails(**order)
    order['items'] = group_items(order['items'], ['sku'])
    return OrderSummary(**order)
