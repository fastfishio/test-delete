import datetime
import json
import logging
import uuid
from decimal import Decimal
from typing import Dict, List

from jsql import sql
from noonutil.v2 import sqlutil

from liborder import ctx, models, domain
from liborder.domain import helpers, serviceability
from liborder.domain.enums import PaymentMethod, SessionOwnerType, Status
from liborder.domain.payment import is_cvv_required
from liborder.domain.preference import DeliveryPreference, get_session_delivery_preferences
from libexternal import customer
from libutil import util
from libutil.translation import _
from libutil.util import equal_decimals

logger = logging.getLogger(__name__)


class Item(util.NoonBaseModel):
    id_partner: int
    sku: str
    qty: int
    qty_max: int = None
    price: Decimal
    image_key: str = None
    title: str = None
    brand: str = None


# Do we need to add a reason for qty change? i.e. it changed due to stock_limit or stock?
class UpdatedItem(util.NoonBaseModel):
    sku: str
    old_qty: int = None
    old_price: Decimal = None


class OrderSummaryEntry(util.NoonBaseModel):
    title: str
    value: str


class OrderSummarySection(util.NoonBaseModel):
    entries: List[OrderSummaryEntry]


class Action(util.NoonBaseModel):
    text: str
    action: str


class SessionMessage(util.NoonBaseModel):
    type: str
    title: str = None
    text: str
    icon: str = None
    actions: List[Action] = None
    bg_color: str = None


class SessionDetails(util.NoonBaseModel):
    session_code: str = None
    user_type: str
    user_id: str
    items: List[Item]
    country_code: str
    currency_code: str = None
    customer_uphone_code: str = None
    payment_method_code: str = None
    order_subtotal: Decimal
    order_total: Decimal
    order_payment_amount: Decimal
    credit_amount: Decimal = Decimal(0)
    payment_token: str = None
    credit_card_bin: str = None
    credit_card_mask: str = None
    cc_type: str = None
    available_payment_methods: List
    is_cod_allowed: bool = True
    is_cvv_required: bool = True
    address_key: str = None
    order_delivery_fee: Decimal
    delivery_preferences: List[DeliveryPreference]
    # estimated delivery would be None when refresh is not required (On PDP, PLP, etc)
    estimated_delivery_text: str = None
    estimated_delivery_at: datetime.datetime = None
    # When session is refreshed, any changes to price/stock is specified in updated_skus
    updated_skus: List[UpdatedItem] = None
    available_payment_methods: List[str]
    order_summary: List[OrderSummarySection]
    messages: List[SessionMessage] = []

    @property
    def total_items(self):
        return sum(item.qty for item in self.items)


class GetOrCreate(util.NoonBaseModel):
    # Refresh should be set to False when on any page that doesn't show the cart items
    refresh: bool = True

    def execute(self, force_create=False) -> SessionDetails:
        session = self.get_active_session(force_create=force_create)
        # Do not refresh if it's a skeleton session
        if self.refresh and session['session_code']:
            return self.refresh_session(session)
        return format_session(session)

    def get_active_session(self, force_create=False):

        service = serviceability.GetServiceability().execute()

        assert ctx.visitor_id, "visitor_id must be set"
        assert service.serviceable, "area is not serviceable"

        return self.get_active_session_for(
            ctx.customer_code, ctx.visitor_id, with_items=True, force_create=force_create
        )

    @staticmethod
    def add_delivery_estimates(session):
        now = datetime.datetime.utcnow()

        # TODO: @akash to clean this with a better estimate logic
        session['estimated_delivery_at'] = now + datetime.timedelta(minutes=30)
        session['estimated_delivery_text'] = f'<b>30 mins</b>'
        return session

    def get_active_session_for(self, customer_code, visitor_id, with_items=False, force_create=False):
        identity_tuple_list = [(SessionOwnerType.GUEST.value, visitor_id)]
        if customer_code:
            identity_tuple_list.append((SessionOwnerType.CUSTOMER.value, customer_code))
        rows = sql(
            ctx.conn,
            '''
            SELECT
                id_session,
                session_code,
                user_type,
                user_id,
                country_code,
                payment_method_code,
                payment_token,
                is_cvv_required,
                credit_card_bin,
                credit_card_mask,
                cc_type,
                credit_amount,
                address_key,
                customer_uphone_code,
                is_active,
                currency_code,
                time_zone
                {% if with_items %},
                id_session_item,
                id_partner,
                sku,
                price,
                qty
                {% endif %}
            FROM session
            {% if with_items %}
                LEFT JOIN session_item USING(id_session)
            {% endif %}
            LEFT JOIN country USING(country_code)
            WHERE (user_type, user_id) IN :identity_tuple_list
            AND country_code = :country_code
            AND is_active = 1
        ''',
            identity_tuple_list=identity_tuple_list,
            country_code=ctx.country_code,
            with_items=with_items,
        ).dicts()

        customer_session = [row for row in rows if row['user_type'] == SessionOwnerType.CUSTOMER.value]
        guest_session = [row for row in rows if row['user_type'] == SessionOwnerType.GUEST.value]
        if customer_session and not guest_session:
            session = customer_session
        elif guest_session and customer_code:
            updated_session = self.switch_to_customer_session(customer_code, visitor_id)
            if updated_session:
                return updated_session
            for row in guest_session:
                row['user_type'] = SessionOwnerType.CUSTOMER.value
                row['user_id'] = customer_code
            session = guest_session
        elif guest_session:
            session = guest_session
        else:  # No guest session and no customer session
            user_type = SessionOwnerType.GUEST.value if not customer_code else SessionOwnerType.CUSTOMER.value
            user_id = visitor_id if not customer_code else customer_code
            session_code = None if not force_create else str(uuid.uuid4())
            skeleton_session = {
                'session_code': session_code,
                'user_type': user_type,
                'user_id': user_id,
                'country_code': ctx.country_code,
                'address_key': ctx.address_key,
                'credit_amount': Decimal(0),
                'payment_method_code': None,
                'credit_card_mask': None,
            }
            if force_create:
                id_session = sqlutil.insert_one(ctx.conn, models.tables.Session, skeleton_session).lastrowid
                skeleton_session['id_session'] = id_session
                if user_type == 'customer':
                    updated_session = set_default_payment_method_for(user_id)
                    if updated_session:
                        return updated_session
                skeleton_session['currency_code'] = helpers.get_country_details_map()[ctx.country_code.lower()][
                    'currency_code'
                ]
            session = [skeleton_session]
        items = [item for item in session if item.get('sku') and item.get('qty', 0) > 0]
        session = session[0].copy()
        session['items'] = items
        # TODO: @akash Fix this once concept of delivery fee is handled appropriately or tests can work without it
        session['order_delivery_fee'] = 10

        if ctx.address_key != session['address_key'] and session['session_code']:

            def set_address_key(modified_session):
                if not ctx.address_key:
                    modified_session['address_key'] = None
                else:
                    assert modified_session['user_type'] == 'customer', 'Guest cant set address key'
                    address = customer.get_customer_address(address_key=ctx.address_key)
                    assert address.customer_code == modified_session['user_id'], 'Invalid address'
                    modified_session['address_key'] = ctx.address_key
                    modified_session['customer_uphone_code'] = address.uphone_code

            session = modify_session(set_address_key, session=session)

        session = self.add_delivery_estimates(session)

        wh_code = helpers.get_warehouses_for_country(ctx.country_code)[0]['wh_code']
        # TODO: @akash Update logic of selecting just 1 warehouse
        skus = [(item['sku'], wh_code) for item in items]
        enriched_offers = helpers.enrich_offers(skus)
        for item in items:
            enriched_item = enriched_offers.get((item['sku'], wh_code))
            enrich_fields = ['image_key', 'title', 'brand', 'qty_max', 'stock_customer_limit']
            for field in enrich_fields:
                item[field] = enriched_item[field]
        return session

    def get_or_create_session(self, user_type, user_id, wh_code, force_create=False):
        session = self.get_active_session_for(user_type, user_id, with_items=True)
        if session:
            return session
        session_code = None
        if force_create:
            session_code = str(uuid.uuid4())
        new_session = {
            'session_code': session_code,
            'user_type': user_type,
            'user_id': user_id,
            'wh_code': wh_code,
            'country_code': ctx.country_code,
            'address_key': ctx.address_key,
            'credit_amount': Decimal(0),
            'payment_method_code': None,
            'credit_card_mask': None,
        }
        if force_create:
            sqlutil.insert_one(ctx.conn, models.tables.Session, new_session)
            if user_type == 'customer':
                set_default_payment_method_for(user_id)
            return self.get_active_session_for(user_type, user_id, with_items=True)
        return [new_session]

    # when a customer logs in, we need switch their session from ('guest', visitor_id) to ('customer', customer_code)
    # and deactivate the old customer session
    @staticmethod
    def switch_to_customer_session(customer_code, visitor_id):
        deactivate_session(SessionOwnerType.CUSTOMER, customer_code)
        sql(
            ctx.conn,
            '''
            UPDATE session
            SET user_type = 'customer', user_id = :customer_code
            WHERE user_type = 'guest'
            AND user_id = :visitor_id
            AND country_code = :country_code
            AND is_active = 1
        ''',
            customer_code=customer_code,
            visitor_id=visitor_id,
            country_code=ctx.country_code,
        )
        return set_default_payment_method_for(customer_code)

    @staticmethod
    def refresh_session(session_to_refresh):
        def refresh_fn(session):
            id_session = session['id_session']

            skus = [item['sku'] for item in session['items']]
            changed_items = []
            final_items = []

            if skus:
                wh_code = helpers.get_warehouses_for_country(ctx.country_code)[0]['wh_code']
                keys = [(sku, wh_code) for sku in skus]
                enriched_items = helpers.enrich_offers(keys)
                for item in session['items']:
                    is_changed = False
                    new_item = {**item, 'id_session': id_session}
                    enriched_item = enriched_items.get((item['sku'], wh_code))
                    if not enriched_item:
                        item['qty'] = 0
                        continue
                    if not equal_decimals(item['price'], enriched_item['price']):
                        is_changed = True
                        new_item['old_price'] = item['price']
                        item['price'] = enriched_item['price']
                        new_item['price'] = item['price']
                    if item['qty'] > min(enriched_item['stock_net'], enriched_item['stock_customer_limit']):
                        is_changed = True
                        new_item['old_qty'] = item['qty']
                        item['qty'] = min(enriched_item['stock_net'], enriched_item['stock_customer_limit'])
                        new_item['qty'] = item['qty']
                    if is_changed:
                        changed_items.append(new_item)
                    final_items.append(item)
            session['updated_skus'] = [item for item in changed_items]
            return session

        return format_session(modify_session(refresh_fn, session_to_refresh))


def deactivate_session(user_type: SessionOwnerType, user_id: str):
    logger.info(f"deactivating session after placing order: user_id: {user_id}")
    sql(
        ctx.conn,
        '''
        UPDATE session SET is_active = NULL
        WHERE user_type = :user_type
        AND user_id = :user_id
        AND country_code = :country_code
        AND is_active = 1
    ''',
        user_type=user_type.value,
        user_id=user_id,
        country_code=ctx.country_code,
    )


def activate_session(session_code):
    sql(
        ctx.conn,
        '''
        UPDATE session SET is_active = 1
        WHERE session_code = :session_code
    ''',
        session_code=session_code,
    )


def set_default_payment_method_for(customer_code):
    default_payment = sql(
        ctx.conn,
        '''
        SELECT payment_method_code, credit_card_mask, payment_token
        FROM customer_default_payment
        WHERE customer_code = :customer_code
        AND country_code = :country_code
        AND is_active = 1
    ''',
        customer_code=customer_code,
        country_code=ctx.country_code,
    ).dict()
    if default_payment:
        return SetPaymentMethod(
            payment_method_code=default_payment['payment_method_code'],
            payment_token=default_payment['payment_token'],
            credit_card_mask=default_payment['credit_card_mask'],
        ).execute(format=False)


class AddItem(util.NoonBaseModel):
    sku: str
    qty: int = 1

    def execute(self):
        assert self.qty > 0, "Invalid item quantity"

        def add_item(session):
            if 'messages' not in session:
                session['messages'] = []
            '''
            TODO: @akash Currently taking first warehouse, this needs to be improved and paired with catalog
            Based on sku and qty, we should find out which warehouses to assign first for each item, and enrichment should build on top of that
            Optionally, wh_code can come in request too for tiny speedup, but maybe not a good idea?
            '''
            # TODO: @akash Handle edge cases for below logic
            wh_code = helpers.get_warehouses_for_country(ctx.country_code)[0]['wh_code']
            enriched_items = helpers.enrich_offers(
                [(self.sku, wh_code)] + [(item['sku'], wh_code) for item in session['items']]
            )
            new_item = enriched_items.get((self.sku, wh_code))
            assert new_item, "Invalid sku"
            assert new_item['wh_code'] == wh_code, "Item does not exist in any warehouse"

            popup_msg = None
            existing = False

            # TODO: Recheck if this works
            stock_limit = new_item['qty_max']
            qty_to_add = min(stock_limit, self.qty)

            if qty_to_add < self.qty:
                if qty_to_add == stock_limit:
                    popup_msg = _('Could not add all of the requested quantity as it exceeds the available stock')
                else:
                    popup_msg = _('Could not add all of the requested quantity as it exceeds the cart size limit')

            for item in session['items']:
                if item['sku'] == self.sku:
                    item['qty'] = max(0, item['qty'] + qty_to_add)
                    existing = True
            if not existing and qty_to_add > 0:
                session['items'].append({**new_item, 'qty': qty_to_add})

            if popup_msg:
                session['messages'].append(
                    {
                        'type': 'popup',
                        'title': 'Could not add to cart',
                        'text': popup_msg,
                        'actions': [{'text': 'View Cart', 'action': 'cart'}],
                    }
                )

        return format_session(modify_session(add_item))


class SetQuantity(util.NoonBaseModel):
    sku: str
    qty: int

    # setting a specific quantity for an item from cart page using dropdown instead of add qty
    def execute(self):
        assert self.qty is not None and self.qty >= 0, "Invalid item quantity"

        def set_qty(session):
            wh_code = helpers.get_warehouses_for_country(ctx.country_code)[0]['wh_code']
            if 'messages' not in session:
                session['messages'] = []
            enriched_items = helpers.enrich_offers(
                [(self.sku, wh_code)] + [(item['sku'], wh_code) for item in session['items']]
            )
            new_item = enriched_items.get((self.sku, wh_code))
            assert new_item, "Invalid sku"
            assert new_item['wh_code'] == wh_code, "Item does not exist in this warehouse"

            popup_msg = None
            existing = False
            stock_limit = new_item['qty_max']

            qty_to_set = min(stock_limit, self.qty)

            if qty_to_set < self.qty:
                if qty_to_set == stock_limit:
                    popup_msg = _('Could not set the requested quantity as it exceeds the available stock')
                else:
                    popup_msg = _('Could not set the requested quantity as it exceeds the cart size limit')

            for item in session['items']:
                if item['sku'] == self.sku:
                    item['qty'] = max(qty_to_set, 0)
                    existing = True
            if not existing and qty_to_set > 0:
                session['items'].append({**new_item, 'qty': qty_to_set})

            if popup_msg:
                session['messages'].append(
                    {
                        'type': 'popup',
                        'title': 'Could not add to cart',
                        'text': popup_msg,
                        'actions': [{'text': 'View Cart', 'action': 'cart'}],
                    }
                )

        return format_session(modify_session(set_qty))


class RemoveItem(util.NoonBaseModel):
    sku: str

    def execute(self):
        def remove_item(session):
            wh_code = helpers.get_warehouses_for_country(ctx.country_code)[0]['wh_code']
            removed_item = helpers.enrich_offers([(self.sku, wh_code)]).get((self.sku, wh_code))
            assert removed_item, "Invalid sku"
            assert removed_item['wh_code'] == wh_code, "Item does not exist in this warehouse"
            for item in session['items']:
                if item['sku'] == self.sku:
                    item['qty'] = 0
                    break

        return format_session(modify_session(remove_item))


'''
In case payment-intent/complete fails or payment flow is interrupted, 
app would call this endpoint
to reset the previous checkout session

This is very messy with lot of queries, try to optimize it
'''


# todo: add a test case for this
class ResetCheckoutSession(util.NoonBaseModel):
    def execute(self):
        assert ctx.customer_code, 'Only logged in users can reset session'
        # we need to get the latest session for the user
        session_order = sql(
            ctx.conn,
            '''
            SELECT session_code, order_nr 
            FROM session_order so
            JOIN session USING (session_code)
            WHERE user_type = 'customer' 
            AND user_id = :user_id
            AND so.is_active = 1
            ORDER BY id_session DESC
            LIMIT 1
        ''',
            user_id=ctx.customer_code,
        ).dict()
        if not session_order:
            logger.warning(f"invalid session reset request for {ctx.customer_code}")
            return
        order_nr = session_order['order_nr']
        order_details = domain.order.GetDetails(order_nr=order_nr).execute(internal=True, formatted=False)
        if order_details["status_code_order"] != Status.PENDING.value:
            logger.warning(f"invalid session reset request for {ctx.customer_code} - order_nr: {order_nr}")
            return

        domain.order.reactivate(order_details, session_code=session_order['session_code'])


class ResetPaymentMethod(util.NoonBaseModel):
    def execute(self):
        def reset_payment_method(session):
            session['payment_method_code'] = None
            session['payment_token'] = None
            session['credit_card_mask'] = None
            session['credit_card_bin'] = None
            session['cc_type'] = None
            session['credit_amount'] = 0

        return format_session(modify_session(reset_payment_method))


class SetPaymentMethod(util.NoonBaseModel):
    payment_method_code: str = None
    credit_amount: Decimal = Decimal('0')
    credit_card_mask: str = None
    payment_token: str = None

    def execute(self, format=True):
        def set_payment_method(session):
            if self.payment_method_code:
                assert self.payment_method_code in [pm.value for pm in PaymentMethod], _("Invalid Payment Method")
                session['payment_method_code'] = self.payment_method_code
            session['payment_method_code'] = self.payment_method_code
            assert self.credit_amount >= 0, _("Credits Amount must not be negative")
            session['credit_amount'] = self.credit_amount
            session['credit_card_mask'] = self.credit_card_mask
            session['payment_token'] = self.payment_token
            session['credit_card_bin'] = util.get_cc_bin(self.credit_card_mask) if self.credit_card_mask else None
            session['cc_type'] = util.get_credit_card_type(session['credit_card_mask'])
            if session['payment_method_code'] == PaymentMethod.COD.value:
                session['credit_card_mask'] = None
                session['payment_token'] = None
                session['credit_card_bin'] = None
                session['cc_type'] = None
            session['is_cvv_required'] = is_cvv_required(session)

        if not format:
            return modify_session(set_payment_method)
        return format_session(modify_session(set_payment_method))


class SetDeliveryPreferences(util.NoonBaseModel):
    delivery_preferences: Dict[str, int]

    def execute(self) -> SessionDetails:
        session = GetOrCreate().get_active_session(force_create=True)
        id_session = session['id_session']
        sql(ctx.conn, "DELETE FROM session_delivery_preference WHERE id_session = :id_session", id_session=id_session)
        delivery_preferences_rows = [
            {
                'id_session': id_session,
                'id_delivery_preference': models.util.get_id_by_code('delivery_preference', dp[0]),
            }
            for dp in self.delivery_preferences.items()
            if dp[1] == 1
        ]
        sqlutil.insert_batch(ctx.conn, models.tables.SessionDeliveryPreference, delivery_preferences_rows)
        return format_session(session)


def format_session(session) -> SessionDetails:
    session['items'] = [item for item in session['items'] if item['qty'] > 0]
    session['order_subtotal'] = sum(item['price'] * item['qty'] for item in session['items'])
    session['order_total'] = session['order_subtotal'] + session['order_delivery_fee']
    session['order_payment_amount'] = max(0, session['order_total'] - session['credit_amount'])
    is_cod = session['payment_method_code'] == PaymentMethod.COD.value
    session['delivery_preferences'] = get_session_delivery_preferences(session['session_code'], postpaid=is_cod)
    session['available_payment_methods'] = ["cc_noonpay", "apple_pay"]
    session['is_cod_allowed'] = True
    session['cc_type'] = util.get_credit_card_type(session['credit_card_mask'])
    session['is_cvv_required'] = is_cvv_required(session)
    session['order_summary'] = get_session_order_summary(session)
    return SessionDetails(**session)


def modify_session(fn, session=None):
    if not session:
        # session is being modified, so its time to create it
        session = GetOrCreate().get_active_session(force_create=True)
    id_session = session['id_session']

    prev_items_map = {item['sku']: (item['qty'], item['price']) for item in session['items']}
    prev_session = session.copy()
    fn(session)
    changed_cols = [key for key in session.keys() if key != 'items' and session[key] != prev_session.get(key)]
    changed_cols = set(changed_cols) & set(models.tables.Session.__table__.columns.keys())
    cur_items_map = {item['sku']: (item['qty'], item['price']) for item in session['items']}

    skus_to_update = []
    for sku in cur_items_map.keys():
        if prev_items_map.get(sku, (-1, -1)) != cur_items_map[sku]:
            skus_to_update.append(sku)
    if skus_to_update:
        items_to_update = [
            dict(item, **{'id_session': id_session}) for item in session['items'] if item['sku'] in skus_to_update
        ]
        logger.info(
            f"items to update: {[(item['sku'], item['price'], item['qty']) for item in items_to_update]}, {prev_items_map}, {cur_items_map}"
        )
        sqlutil.upsert(
            ctx.conn,
            models.tables.SessionItem,
            items_to_update,
            unique_columns=['id_session', 'sku'],
            insert_columns=['id_session', 'sku', 'id_partner', 'price', 'qty'],
            update_columns=['qty', 'price'],
        )
    if changed_cols:
        sqlutil.upsert_one(ctx.conn, models.tables.Session, session)
    session['items'] = [item for item in session['items'] if item['qty'] > 0]
    return session


def get_session_order_summary(session) -> List[OrderSummarySection]:
    num_items = sum([item['qty'] for item in session['items']])
    if not num_items:
        return []
    item_text = f'{_("Subtotal")} ({num_items} {_("Items") if num_items > 1 else _("Item")})'
    credits = min(session['credit_amount'], session['order_total'])
    balance = session["order_total"] - credits
    delivery_fee_text = str(util.decimal_round(session["order_delivery_fee"], replace_zero=True))
    if delivery_fee_text != 'FREE':
        delivery_fee_text = f'{session["currency_code"]} {delivery_fee_text}'
    sections = []
    section1 = [
        OrderSummaryEntry(
            title=item_text, value=f'{session["currency_code"]} {util.decimal_round(session["order_subtotal"])}'
        ),
        OrderSummaryEntry(title=_('Shipping'), value=delivery_fee_text),
    ]
    sections.append(OrderSummarySection(entries=section1))
    if session["credit_amount"] > 0:
        sections += [
            OrderSummarySection(
                entries=[
                    OrderSummaryEntry(
                        title=f'<b>{_("Cart total")}</b>',
                        value=f'<b>{session["currency_code"]} {util.decimal_round(session["order_total"])}</b>',
                    ),
                    OrderSummaryEntry(
                        title=_('Noon credits'), value=f'- {session["currency_code"]} {util.decimal_round(credits)}'
                    ),
                ]
            ),
            OrderSummarySection(
                entries=[
                    OrderSummaryEntry(
                        title=f'<b>{_("Balance")}</b>',
                        value=f'<b>{session["currency_code"]} {util.decimal_round(balance)}</b>',
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
                        value=f'<b>{session["currency_code"]} {util.decimal_round(session["order_total"])}</b>',
                    )
                ]
            )
        )
    return sections
