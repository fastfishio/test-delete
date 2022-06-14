from pydantic import Field
import json
import logging
import random
import string
from datetime import datetime, timedelta
from decimal import Decimal as D
from typing import Any, Dict, List

from jsql import sql
from liborder.domain.order import OrderDetailsInternal
from noonutil.v1 import miscutil
from noonutil.v2 import sqlutil

import libaccess
from libcs import with_permission
from libcs.domain.enums import ActionType
from libexternal import customer
from liborder import domain
from liborder.context import ctx, Context
from liborder.domain import enums
from liborder.domain import helpers
from liborder.domain.boilerplate_event import ActionCode, create_event
from liborder.domain.payment import PAYMENT_METHOD_MAP
from liborder.domain.status import ORDER_TERMINAL_STATES
from liborder.models import tables, util as order_util
from libutil import util
from libutil.translation import _

from ..models.dtos import *

logger = logging.getLogger(__name__)


class GetDetails(util.NoonBaseModel):
    order_nr: str

    @with_permission(libaccess.Permission.CS_ORDER_DETAILS)
    def execute(self):
        order = domain.order.GetDetails(order_nr=self.order_nr).execute(internal=True, formatted=False, local_tz=True)
        formatted_order = domain.order.format_order(order, internal=True)
        country_details = helpers.get_country_details_map()[formatted_order.country_code.lower()]
        currency_code = country_details['currency_code']
        time_zone = country_details['time_zone']
        tz_delta = util.get_delta_from_tz(time_zone)
        adjustments = get_order_adjustments(self.order_nr, currency_code)
        item_adjustment_map = {
            adjustment.item_nr: adjustment.amount for adjustment in adjustments if adjustment.item_nr
        }
        warehouse_history = get_order_history_events(
            order['id_sales_order'], tz_delta, enums.SalesOrderHistoryEventType.ORDER_STATUS
        )
        logistics_history = get_order_history_events(
            order['id_sales_order'], tz_delta, enums.SalesOrderHistoryEventType.LOGISTICS
        )
        logistics_history_map = {e.event: e.time for e in logistics_history}
        eta_history = sql(
            ctx.conn,
            '''
            SELECT
                CONVERT_TZ(estimated_delivery_at, 'UTC', :time_zone) as estimated_delivery_at
            FROM order_eta_history
            WHERE id_sales_order = :id_sales_order
            ORDER BY created_at
        ''',
            id_sales_order=order['id_sales_order'],
            time_zone=time_zone,
        ).dicts()
        available_etas = ['estimated_delivery_at']
        eta_to_logistics_history_map = {'estimated_delivery_at': 'delivered'}
        delivery_history = []
        for eta in available_etas:
            time_actual = logistics_history_map.get(eta_to_logistics_history_map[eta])
            time_actual = datetime.utcfromtimestamp(time_actual) + tz_delta if time_actual else eta_history[-1].get(eta)
            time_estimated = eta_history[0].get(eta)

            status = 'red' if time_estimated and time_actual and time_estimated < time_actual else 'green'

            delivery_history.append(
                CSEstimate(
                    event=eta_code_to_name(eta), time_estimated=time_estimated, time_actual=time_actual, status=status
                )
            )

        address_details = customer.get_customer_address(order['address_key'])
        customer_details = [
            CSDataPoint(title='Name', value=f"{address_details.first_name} {address_details.last_name}"),
            CSDataPoint(title='Code', value=order['customer_code']),
            CSDataPoint(title='Phone', value=address_details.phone),
            CSDataPoint(title='Address', value=address_details.street_address),
            CSDataPoint(title='Issued Noon Credits', value=f"{currency_code} {order['order_issued_credit']}"),
        ]
        payment_info = [
            CSDataPoint(title='Amount Captured in Credits', value=f"{currency_code} {order['order_credit_captured']}"),
            CSDataPoint(title='Cash to be collected', value=f"{currency_code} {order['order_payment_cash_amount']}"),
            CSDataPoint(title='Authorized Amount', value=f"{currency_code} {order['order_payment_authorized']}"),
            CSDataPoint(title='Authorized Captured', value=f"{currency_code} {order['order_payment_captured']}"),
            CSDataPoint(title='Total Payment Adjustments', value=f"{currency_code} {order['order_mp_adjustment']}"),
            CSDataPoint(title='Refunded to Card', value=f"{currency_code} {order['order_payment_refunded']}"),
            CSDataPoint(title='Cash Collected', value=f"{currency_code} {order['order_payment_cash_collected']}"),
        ]
        cs_items = []
        warehouse = helpers.get_warehouse_details(formatted_order.country_code, formatted_order.wh_code)
        warehouse_location = Location(lat=warehouse['lat'], lng=warehouse['lng'])
        warehouse_details = [
            CSDataPoint(title='Warehouse Code', value=formatted_order.wh_code),
            CSDataPoint(title='Country Code', value=formatted_order.country_code),
            CSDataPoint(title='City', value=warehouse['city_en']),
            CSDataPoint(title='Area', value=warehouse['area_name_en']),
        ]
        for item in formatted_order.items:
            data_points = [
                CSDataPoint(title='SKU', value=item.sku),
                CSDataPoint(title='Item Number', value=item.item_nr),
                CSDataPoint(
                    title='Item Adjustment Amount', value=f"{currency_code} {item_adjustment_map.get(item.item_nr, 0)}"
                ),
            ]
            cs_item = CSOrderItem(
                image_key=item.image_key,
                status=item.status,
                brand=item.brand,
                title=item.title,
                price=item.price,
                discounted_price=None,
                details=data_points,
                sku=item.sku,
                item_nr=item.item_nr,
                adjustment_amount=item_adjustment_map.get(item.item_nr, 0),
            )
            cs_items.append(cs_item)
        delivered_at = logistics_history_map.get('delivered')
        delivered_at = datetime.utcfromtimestamp(delivered_at) + tz_delta if delivered_at else None
        delivery_ETA = delivered_at or eta_history[-1]['estimated_delivery_at']
        delivery_status_time = delivered_at or (datetime.utcnow() + tz_delta)
        delivery_status = 'On Time' if delivery_status_time <= order['original_estimated_delivery_at'] else 'Delayed'
        return CSOrder(
            order_nr=order['order_nr'],
            order_placed=formatted_order.placed_at,
            delivery_ETA=delivery_ETA,
            delivery_status=delivery_status,
            delivery_history=delivery_history,
            warehouse_history=warehouse_history,
            logistics_history=logistics_history,
            customer_details=customer_details,
            customer_code=formatted_order.customer_code,
            order_status_code=formatted_order.status_code,
            order_status=formatted_order.status,
            payment_info=payment_info,
            payment_method=PAYMENT_METHOD_MAP.get(order['payment_method_code']).get('en'),
            warehouse_details=warehouse_details,
            warehouse_location=warehouse_location,
            order_summary=get_cs_order_summary(order),
            initial_order_summary=get_cs_order_summary(order, initial_summary=True),
            items=cs_items,
            adjustments=adjustments,
            comments=get_order_comments(self.order_nr),
            is_cancelable=order['is_cancelable'],
            action_log=get_order_action_log(self.order_nr),
        )


class AddComment(util.NoonBaseModel):
    comment: str = Field(min_length=1, max_length=1000)
    order_nr: str

    @with_permission(libaccess.Permission.CS_ORDER_COMMENT)
    def execute(self):
        order_util.validate_order_nr(self.order_nr)
        comment_dict = {
            'order_nr': self.order_nr,
            'comment_code': generate_comment_code(),
            'user_code': ctx.user_code,
            'comment': self.comment,
        }

        sqlutil.insert_one(ctx.conn, tables.CSOrderComment, comment_dict)


class CancelOrder(util.NoonBaseModel):
    order_nr: str
    # reason_code is not used right now
    reason_code: Optional[str]
    comment: Optional[str] = Field(max_length=1000)

    @with_permission(libaccess.Permission.CS_CANCEL_ORDER)
    def execute(self):
        cancel_reason = next((reason for reason in get_cancel_reasons() if reason.code == self.reason_code), None)
        assert cancel_reason is not None, "Invalid cancel reason code"

        domain.order.cancel_order(self.order_nr, self.reason_code)
        log_action(order_nr=self.order_nr, action_type=ActionType.cs_order_cancelation, reason=cancel_reason.reason)

        if self.comment:
            comment_dict = {
                'order_nr': self.order_nr,
                'comment_code': generate_comment_code(),
                'user_code': ctx.user_code,
                'comment': self.comment,
            }

            sqlutil.insert_one(ctx.conn, tables.CSOrderComment, comment_dict)


MAX_ISSUED_CREDIT_PERCENT = D(1.25)


class IssueCredit(util.NoonBaseModel):
    order_nr: str
    amount: D = Field(gt=0)
    reason: str = Field(min_length=1, max_lenght=200)

    @with_permission(libaccess.Permission.CS_ISSUE_CREDIT)
    def execute(self):
        order_details: OrderDetailsInternal = domain.order.GetDetails(order_nr=self.order_nr).execute(internal=True)
        assert datetime.now() < (order_details.placed_at + timedelta(days=2)), 'Order too old to issue credits'
        assert order_details.order_issued_credit <= self.amount, 'cannot issue less credits than already issued'
        # here it should be initial order total?
        order_total = order_details.initial_order_total
        assert (
            self.amount <= order_total * MAX_ISSUED_CREDIT_PERCENT
        ), f'Credit amount too high - subtotal: {order_total}'
        domain.credit.set_issued_credits(self.order_nr, self.amount)
        create_event(ActionCode.CAPTURE_ISSUED_CREDITS, {'order_nr': self.order_nr})
        log_action(
            order_nr=self.order_nr,
            action_type=ActionType.credits_issued,
            reason=self.reason,
            amount=f'{order_details.currency_code} {util.decimal_round(self.amount)}',
        )


class AddAdjustment(util.NoonBaseModel):
    reason_code: str
    order_nr: str
    item_nr: Optional[str]
    comment: Optional[str] = Field(max_length=1000)

    @with_permission(libaccess.Permission.CS_ADJUST_PAYMENT)
    def execute(self):
        '''
        Customer Support will not enter the amount to be adjusted.
        They can select an item to be refunded and BE would take the price paid for the item
        and add adjustment accordingly

        Other scenarios would be shipping fee refund or cod fee refund
        here also, CS would not enter the amount, but BE would infer that from the reason code
        and order details to figure out what to adjust
        '''
        adjustment_reasons = get_adjustment_reasons()
        adjustment_reason_map = {reason['reason_code']: reason for reason in adjustment_reasons}
        self.item_nr = self.item_nr if self.item_nr is not None else ''
        assert self.reason_code in adjustment_reason_map, "Invalid reason"
        adjustment = {
            'order_nr': self.order_nr,
            'adjustment_reason_code': self.reason_code,
            'comment': self.comment,
            'item_nr': self.item_nr,
            'user_code': ctx.user_code,
        }
        order_details = domain.order.GetDetails(order_nr=self.order_nr).execute(internal=True)
        assert (
            order_details.status_code == enums.Status.DELIVERED.value
        ), 'You can only add adjustments when order is delivered'
        assert datetime.now() < (
            order_details.placed_at + timedelta(days=7)
        ), 'Order is older than 7 days, cannot do adjustment'
        reason = adjustment_reason_map[self.reason_code]
        if reason.adjustment_type == AdjustmentType.item.value:
            assert self.item_nr, 'Item number cannot be null for reason code: item'
            item_ref = None
            for item in order_details.items:
                if item.item_nr == self.item_nr:
                    item_ref = item
                    adjustment['amount'] = -item.price
            assert item_ref, f'Invalid item number: {self.item_nr}'
            assert not item_ref.cancel_reason, 'cannot add adjustment for canceled item'
            # just a safety check
            assert adjustment['amount'] < 0, 'Invalid adjustment amount'
            sqlutil.upsert(
                ctx.conn,
                tables.CSOrderAdjustment,
                [adjustment],
                update_columns=['comment', 'amount', 'user_code', 'adjustment_reason_code'],
                unique_columns=['order_nr', 'item_nr'],
            )
        else:
            assert not self.item_nr, 'item_nr should be null for adjustment_type != "item"'
            assert (
                reason.adjustment_type == AdjustmentType.order.value
            )  # , 'Invalid reason selected for order level adjustment'
            if self.reason_code == "shipping_fee_refund":
                assert order_details.order_delivery_fee > 0, 'Delivery Fee charged was already 0. cannot refund'
                adjustment['amount'] = -order_details.order_delivery_fee

            # just a safety check
            assert adjustment['amount'] < 0, 'Invalid adjustment amount'
            sqlutil.upsert(
                ctx.conn,
                tables.CSOrderAdjustment,
                [adjustment],
                unique_columns=['order_nr', 'adjustment_reason_code'],
                update_columns=['comment', 'amount', 'user_code', 'item_nr'],
            )

        net_adjustment = sql(
            ctx.conn,
            '''
            SELECT SUM(amount)
            FROM sales_order so
            JOIN cs_order_adjustment coa USING (order_nr)
            WHERE order_nr = :order_nr
        ''',
            order_nr=self.order_nr,
        ).scalar()
        domain.order.modify_order(self.order_nr, {'order_mp_adjustment': net_adjustment}, internal=True)
        if order_details.status_code in ORDER_TERMINAL_STATES:
            create_event(ActionCode.SETTLE_PAYMENT, {'order_nr': self.order_nr})

        log_action(
            order_nr=self.order_nr,
            action_type=ActionType.payment_adjustment,
            reason=adjustment_reason_map[self.reason_code].title,
            amount=f'{order_details.currency_code} {util.decimal_round(adjustment["amount"])}',
            item_nr=self.item_nr,
        )


class DeleteComment(util.NoonBaseModel):
    comment_code: str
    order_nr: str

    @with_permission(libaccess.Permission.CS_ORDER_COMMENT)
    def execute(self):
        order_util.validate_order_nr(self.order_nr)
        order_util.validate_cs_order_comment_code(self.comment_code)
        sql(
            ctx.conn,
            '''
            UPDATE cs_order_comment
            SET is_deleted = 1
            WHERE user_code = :user_code
            AND comment_code = :comment_code
        ''',
            comment_code=self.comment_code,
            user_code=ctx.user_code,
        )


class Search(util.NoonBaseModel):
    query: str = Field(min_length=1)
    limit: Optional[int] = Field(ge=1, le=50)

    @with_permission(libaccess.Permission.CS_ORDER_SEARCH)
    def execute(self):
        limit = self.limit or 50

        self.query = self.query.strip()

        customer_codes_list = None

        if util.is_phone(self.query):
            self.query = self.query.replace('+', '')
            self.query = self.query.replace('-', '')
            customer_codes_list = customer.customer_search_phone(self.query)

        if util.is_email(self.query):
            customer_codes_list = customer.customer_search_email(self.query)

        order_nr_list = sql(
            ctx.conn,
            '''
            SELECT order_nr
            FROM sales_order
            WHERE 
                created_at > UTC_TIMESTAMP() - INTERVAL 480 HOUR
                AND (
                    order_nr LIKE CONCAT('%', :query, '%')
                    OR customer_code LIKE CONCAT('%', :query, '%')
                    {% if customer_codes_list %} OR customer_code IN :customer_codes_list {% endif %}
                )
            ORDER BY created_at DESC
            LIMIT :limit
        ''',
            customer_codes_list=customer_codes_list,
            query=self.query,
            limit=limit,
        ).scalars()

        if order_nr_list is None:
            return SearchResult(orders=[])

        orders = domain.order.ManyOrders(order_nrs=order_nr_list).execute(
            with_customer_info=True, local_tz=True, sort_key='created_at'
        )
        return SearchResult(orders=[OrderSearchDetails(**order) for order in orders])


class EditComment(util.NoonBaseModel):
    comment: str = Field(min_length=1, max_length=1000)
    comment_code: str
    order_nr: str

    @with_permission(libaccess.Permission.CS_ORDER_COMMENT)
    def execute(self):
        order_util.validate_order_nr(self.order_nr)
        order_util.validate_cs_order_comment_code(self.comment_code)
        sql(
            ctx.conn,
            '''
            UPDATE cs_order_comment
            SET comment = :comment
            WHERE user_code = :user_code
            AND comment_code = :comment_code
        ''',
            comment_code=self.comment_code,
            user_code=ctx.user_code,
            comment=self.comment,
        )


def get_cancel_reasons() -> List[CancelReason]:
    reasons = helpers.get_cancel_reasons(internal=1, item_level=0)
    for reason in reasons:
        reason['reason'] = reason['name_en']
    return [CancelReason(**r) for r in reasons]


def eta_code_to_name(eta_code: str) -> str:
    eta = eta_code.replace('estimated_', '')
    eta = eta.replace('_', ' ')
    return eta.title()


def get_order_history_events(
    id_sales_order: int, tz_delta: timedelta, events_type: enums.SalesOrderHistoryEventType
) -> List[CSEvent]:
    sorted_history = sql(
        ctx.conn,
        """SELECT * FROM sales_order_history_event he
    WHERE 
        id_sales_order = :id_sales_order AND
        event_type = :events_type
    ORDER BY time ASC;""",
        id_sales_order=id_sales_order,
        events_type=events_type.value,
    )
    return [CSEvent(event=event['value'], time=(event['time'] + tz_delta)) for event in sorted_history]


def generate_comment_code():
    random_digits = ''.join(random.choices(string.digits + string.ascii_lowercase, k=8))
    date_encoded = util.encode_date()
    tail = 'A' if Context.is_production else 'S'
    return f"C{date_encoded}{random_digits}{tail}".upper()


@miscutil.cached(ttl=60 * 60 * 2)
def get_adjustment_reasons() -> List[CSAdjustmentReason]:
    adjustment_reasons_iter = sql(
        ctx.conn,
        '''
        SELECT
            code as reason_code,
            title,
            adjustment_payer_code,
            adjustment_type
        FROM cs_adjustment_reason
    ''',
    ).dicts_iter()
    adjustment_reasons = []
    for adjustment_reason in adjustment_reasons_iter:
        adjustment_reason['adjustment_type'] = AdjustmentType[adjustment_reason['adjustment_type']]
        adjustment_reasons.append(CSAdjustmentReason(**adjustment_reason))
    return adjustment_reasons


def get_order_adjustments(order_nr: str, currency_code: str) -> List[CSAdjustment]:
    adjustments_iter = sql(
        ctx.conn,
        '''
        SELECT
            adjustment_reason_code as reason_code,
            user_code,
            item_nr,
            comment,
            amount
        FROM cs_order_adjustment
        WHERE order_nr = :order_nr
        ORDER BY created_at ASC
    ''',
        order_nr=order_nr,
    ).dicts_iter()
    adjustments = []
    for adjustment in adjustments_iter:
        adjustment['amount'] = f"{adjustment['amount']} {currency_code}"
        adjustments.append(CSAdjustment(**adjustment))
    return adjustments


def get_order_comments(order_nr) -> List[CSComment]:
    comments_iter = sql(
        ctx.conn,
        '''
        SELECT
            created_at as time,
            user_code as user,
            comment_code,
            comment
        FROM cs_order_comment
        WHERE 
            order_nr = :order_nr AND
            is_deleted = 0
        ORDER BY created_at ASC
    ''',
        order_nr=order_nr,
    ).dicts_iter()
    return [CSComment(**c) for c in comments_iter]


class WhoAmI(util.NoonBaseModel):
    def execute(self) -> CSUser:
        assert ctx.user_code, "Invalid user"
        return CSUser(user_code=ctx.user_code)


def get_cs_order_summary(order, initial_summary=False) -> List[CSOrderSummarySection]:
    num_items = len(order['items'])
    if num_items == 0:
        return []
    item_text = f'{_("Subtotal")} ({num_items} {_("Items") if num_items > 1 else _("Item")})'

    balance = util.decimal_round(order['order_total'] + order['order_credit_captured'])
    delivery_fee_text = str(util.decimal_round(order["order_delivery_fee"]))
    order_subtotal = util.decimal_round(order["order_subtotal"])
    order_total = util.decimal_round(order["order_total"])
    order_credit_captured = util.decimal_round(order["order_credit_captured"])

    if initial_summary:
        balance = util.decimal_round(order['initial_order_total'] + order['order_credit_amount'])
        delivery_fee_text = str(util.decimal_round(order["initial_order_delivery_fee"]))
        order_subtotal = util.decimal_round(order["initial_order_subtotal"])
        order_total = util.decimal_round(order["initial_order_total"])
        order_credit_captured = util.decimal_round(order["order_credit_amount"])

    delivery_fee_text = f'{order["currency_code"]} {delivery_fee_text}'
    sections = []
    section1 = [
        CSOrderSummaryEntry(
            title=item_text,
            title_style='highlight',
            value=f'{order["currency_code"]} {order_subtotal}',
            value_style='highlight',
        ),
        CSOrderSummaryEntry(
            title=_('Shipping'), title_style='highlight', value=delivery_fee_text, value_style='highlight'
        ),
    ]
    sections.append(CSOrderSummarySection(entries=section1))
    if order["order_credit_captured"] < 0:
        sections += [
            CSOrderSummarySection(
                entries=[
                    CSOrderSummaryEntry(
                        title=f'{_("Cart total")}',
                        title_style='bold',
                        value=f'{order["currency_code"]} {order_total}',
                        value_style='bold',
                    ),
                    CSOrderSummaryEntry(
                        title=_('Noon credits'),
                        title_style='highlight',
                        value=f'- {order["currency_code"]} {-order_credit_captured}',
                        value_style='highlight',
                    ),
                ]
            ),
            CSOrderSummarySection(
                entries=[
                    CSOrderSummaryEntry(
                        title=f'{_("Balance")}',
                        title_style='bold',
                        value=f'{order["currency_code"]} {balance}',
                        value_style='bold',
                    )
                ]
            ),
        ]
    else:
        sections.append(
            CSOrderSummarySection(
                entries=[
                    CSOrderSummaryEntry(
                        title=f'{_("Cart total")}',
                        title_style='bold',
                        value=f'{order["currency_code"]} {order_total}',
                        value_style='bold',
                    )
                ]
            )
        )
    return sections


def log_action(order_nr: str, action_type: ActionType, reason: str, item_nr: str = None, amount: str = None):
    action = {
        'order_nr': order_nr,
        'action_type': action_type.value,
        'reason': reason,
        'item_nr': item_nr,
        'amount': amount,
        'user_code': ctx.user_code,
    }
    sqlutil.insert_one(ctx.conn, tables.CSOrderActionLog, action)


def get_order_action_log(order_nr: str) -> List[Action]:
    def get_action_msg(action: Dict[str, Any]) -> str:
        if action['action_type'] == ActionType.credits_issued:
            return f'Issued credits set to {action["amount"]}.'
        if action['action_type'] == ActionType.cs_order_cancelation:
            return f'Order canceled by CS agent.'
        if action['action_type'] == ActionType.payment_adjustment:
            return f'{action["amount"]} was refunded to the customer.'
        return ''

    actions_iter = sql(
        ctx.conn,
        '''
        SELECT * FROM cs_order_action_log
        WHERE order_nr = :order_nr ORDER BY created_at ASC
    ''',
        order_nr=order_nr,
    ).dicts_iter()
    actions = []
    for action in actions_iter:
        action['action_type'] = ActionType[action['action_type']]
        action['action_time'] = action['created_at']
        action['msg'] = get_action_msg(action)
        actions.append(Action(**action))

    return actions
