import datetime
from liborder.domain.enums import SessionOwnerType

import time_machine

from libexternal import customer
from liborder import Context, domain
from liborder.domain import helpers
from decimal import Decimal as D
from libutil.util import equal_decimals
from tests.order import util as testutil
from tests.order.mocks import customer as mocked_customer
from tests.order.mocks import helpers as mocked_helpers
from tests.order.mocks.payment import get_payment_mock
from unittest import mock

WH2_LAT = 252005240
WH2_LNG = 552807372
WH3_LAT = 252105240
WH3_LNG = 552817372


def is_within_minutes(date, minutes, tolerance=1):
    now = datetime.datetime.now()
    start = now + datetime.timedelta(minutes=minutes) - datetime.timedelta(minutes=tolerance)
    end = now + datetime.timedelta(minutes=minutes) + datetime.timedelta(minutes=tolerance)

    return start <= date < end


def test_get_new_session_guest(data_order):
    with Context.service(visitor_id="v1", lat=WH2_LAT, lng=WH2_LNG):
        session = domain.session.GetOrCreate().execute()
        assert session.user_type == "guest", "Incorrect user type"
        assert session.user_id == "v1", "Incorrect user id"
        assert len(session.items) == 0, "Items in new session"
        assert session.estimated_delivery_text == '<b>30 mins</b>', "incorrect estimate text"


def test_get_new_session_customer(data_order):
    with Context.service(visitor_id="v1", customer_code="c1", lat=WH2_LAT, lng=WH2_LNG):
        session = domain.session.GetOrCreate().execute()
        assert session.user_type == "customer", "Incorrect user type"
        assert session.user_id == "c1", "Incorrect user id"
        assert len(session.items) == 0, "Items in new session"


def test_add_to_guest_cart_then_login_and_logout(data_order):
    # First guest session
    with Context.service(visitor_id="v1", lat=WH2_LAT, lng=WH2_LNG):
        session = domain.session.AddItem(sku='Z019FDA9EAE0889BA47A1Z-1').execute()
        assert session.user_type == "guest", "Incorrect user type"
        assert session.user_id == "v1", "Incorrect user id"
        assert session.total_items == 1, "Incorrect item total in cart"
        session = domain.session.AddItem(sku='Z019FDA9EAE0889BA47A1Z-1', qty=2).execute()
        assert session.items[0].sku == "Z019FDA9EAE0889BA47A1Z-1", "Incorrect sku in cart"
        assert session.items[0].qty == 3, "Incorrect qty"
        assert session.total_items == 3, "Incorrect total items"
        assert equal_decimals(session.order_subtotal, 7.95), "Incorrect Order Total"
        assert equal_decimals(session.order_total, 17.95), "Incorrect Total"
    # Now customer logs in
    with Context.service(visitor_id="v1", customer_code="c1", lat=WH2_LAT, lng=WH2_LNG):
        session = domain.session.SetQuantity(sku='Z019FDA9EAE0889BA47A1Z-1', qty=2).execute()
        assert session.user_type == "customer", "Incorrect user type"
        assert session.user_id == "c1", "Incorrect user id"
        assert session.total_items == 2, "Incorrect item total in cart"
        session = domain.session.AddItem(sku='Z019FDA9EAE0889BA47A1Z-1', qty=2).execute()
        assert session.items[0].sku == "Z019FDA9EAE0889BA47A1Z-1", "Incorrect sku in cart"
        assert session.items[0].qty == 4, "Incorrect qty"
        assert session.total_items == 4, "Incorrect total items"
        assert equal_decimals(session.order_subtotal, 10.6), "Incorrect Order Total"
        assert equal_decimals(session.order_total, 20.6), "Incorrect Total"
    # Now customer logs out, his cart should be empty
    with Context.service(visitor_id="v1", lat=WH2_LAT, lng=WH2_LNG):
        session = domain.session.GetOrCreate().execute()
        assert session.user_type == "guest", "Incorrect user type"
        assert session.user_id == "v1", "Incorrect user id"
        assert session.total_items == 0, "Incorrect item total in cart"


# Todo: make different scenarios of this test
# Also Todo: use different SKUs for this test (without interference from indexing)
def test_sessions_with_multiple_warehouses(data_order):
    # Session on warehouse 2
    with Context.service(visitor_id="v1", lat=WH2_LAT, lng=WH2_LNG):
        session = domain.session.AddItem(sku='Z019FDA9EAE0889BA47A1Z-1', qty=2).execute()
        assert session.user_type == "guest", "Incorrect user type"
        assert session.user_id == "v1", "Incorrect user id"
        assert session.total_items == 2, "Incorrect item total in cart"
        assert equal_decimals(session.order_total, 15.3), "Incorrect Total"

    # TODO: @Akash, Re-enable this once we support multiple warehouses
    # # Session on warehouse 3
    # with Context.service(visitor_id="v1", lat=WH3_LAT, lng=WH3_LNG):
    #     session = domain.session.AddItem(sku='Z008431D8F223B31EF128Z-1', qty=10).execute()
    #     assert session.user_type == "guest", "Incorrect user type"
    #     assert session.user_id == "v1", "Incorrect user id"
    #     assert session.total_items == 10, "Incorrect item total in cart"
    #     assert equal_decimals(session.order_total, 110), "Incorrect Total"

    # # Switch back to warehouse 2
    # with Context.service(visitor_id="v1", lat=WH2_LAT, lng=WH2_LNG):
    #     session = domain.session.GetOrCreate().execute()
    #     assert session.total_items == 10, "Incorrect item total in cart"


def test_delivery_preferences(data_order):
    with Context.service(customer_code='c1', visitor_id="v1", lat=WH2_LAT, lng=WH2_LNG):
        session = domain.session.GetOrCreate().execute()
        assert len(session.delivery_preferences) == 2, "Incorrect total delivery preferences"
        assert session.delivery_preferences[0].value == 0, "preference should not be selected"
        assert session.delivery_preferences[1].value == 0, "preference should not be selected"
        session = domain.session.SetDeliveryPreferences(delivery_preferences={'dontring': 1}).execute()
        for preference in session.delivery_preferences:
            assert preference.value == 0 or preference.code == 'dontring', "Only dontring preference should be selected"
        session = domain.session.SetDeliveryPreferences(delivery_preferences={'leaveatdoor': 1}).execute()
        for preference in session.delivery_preferences:
            assert (
                preference.value == 0 or preference.code == 'leaveatdoor'
            ), "Only leaveatdoor preference should be selected"

        session = domain.session.SetPaymentMethod(payment_method_code='cod').execute()
        assert len(session.delivery_preferences) == 1, "Only one pref should be available for postpaid"
        assert session.delivery_preferences[0].code == 'dontring', "dontring should be the only pref"
        for preference in session.delivery_preferences:
            if preference.code == 'dontring':
                assert preference.value == 0, "dontring not selected"


def test_remove_item(data_order):
    with Context.service(visitor_id="v2", lat=WH2_LAT, lng=WH2_LNG):
        session = domain.session.AddItem(sku='Z019FDA9EAE0889BA47A1Z-1', qty=5).execute()
        assert session.total_items == 5, "Incorrect total items"
        session = domain.session.RemoveItem(sku='Z019FDA9EAE0889BA47A1Z-1').execute()
        assert session.total_items == 0, "Incorrect total items"


def test_set_address_details(data_order, monkeypatch):
    monkeypatch.setattr(customer, 'get_customer_address', mocked_customer.get_customer_address)
    # No address key in header, session should not have address key
    with Context.service(visitor_id="v2", customer_code='c1', lat=WH2_LAT, lng=WH2_LNG):
        session = domain.session.GetOrCreate().execute()
        assert not session.address_key, "Address Key Should not be set"
    # Set address key in header
    with Context.service(visitor_id="v2", customer_code='c1', lat=WH2_LAT, lng=WH2_LNG, address_key='A091-1'):
        session = domain.session.GetOrCreate().execute()
        assert session.address_key == 'A091-1', "Address Key Incorrect"
    # Change address key in header
    with Context.service(visitor_id="v2", customer_code='c1', lat=WH2_LAT, lng=WH2_LNG, address_key='A091-2'):
        session = domain.session.GetOrCreate().execute()
        assert session.address_key == 'A091-2', "Address Key Incorrect"
    # remove address key
    with Context.service(visitor_id="v2", customer_code='c1', lat=WH2_LAT, lng=WH2_LNG):
        session = domain.session.GetOrCreate().execute()
        assert not session.address_key, "Address Key Should not be set"


def test_set_payment_method(data_order):
    with Context.service(visitor_id="v2", lat=WH2_LAT, lng=WH2_LNG):
        session = domain.session.SetPaymentMethod(payment_method_code='cod').execute()
        assert session.payment_method_code == 'cod', "Invalid Payment Method"


def test_update_session_prices(data_order):
    with Context.service(visitor_id="v3", lat=WH2_LAT, lng=WH2_LNG):
        session = domain.session.AddItem(sku='Z019FDA9EAE0889BA47A1Z-1', qty=5).execute()
        assert session.total_items == 5, "Incorrect total items"
        session = domain.session.GetOrCreate().execute()
        assert session.total_items == 5, "Incorrect total items"
        assert not session.updated_skus, "No prices should have changed"


def test_price_change(monkeypatch, data_order):
    with Context.service(visitor_id="v4", lat=WH2_LAT, lng=WH2_LNG):
        session = domain.session.AddItem(sku='Z019FDA9EAE0889BA47A1Z-1', qty=5).execute()
        assert session.total_items == 5, "Incorrect total items"
        monkeypatch.setattr(helpers, 'enrich_offers', mocked_helpers.patched_enrich_offers)
        price_update = domain.session.GetOrCreate().execute()
        assert price_update.total_items == 5, "Incorrect total items"
        assert equal_decimals(price_update.updated_skus[0].old_price, 2.65), "prices should have changed"


# TODO: need more tests as there are a lot of cases to consider (limits/stock changing mid session)
def test_cart_limits(data_order):
    # No limits violated
    with Context.service(visitor_id="v1", lat=WH2_LAT, lng=WH2_LNG):
        session = domain.session.AddItem(sku='Z019FDA9EAE0889BA47A1Z-1', qty=10).execute()
        assert session.total_items == 10, "Incorrect item total in cart"
        for message in session.messages:
            assert message.type != 'popup', "No limits are violated"
        domain.session.RemoveItem(sku='Z019FDA9EAE0889BA47A1Z-1').execute()
    # Stock violated
    with Context.service(visitor_id="v1", lat=WH2_LAT, lng=WH2_LNG):
        session = domain.session.AddItem(sku='Z019FDA9EAE0889BA47A1Z-1', qty=13).execute()
        assert session.total_items == 12, "Incorrect item total in cart"
        assert len(session.messages), "limits are violated"
        assert session.messages[-1].type == 'popup', "Incorrect message type"
        assert 'stock' in session.messages[-1].text, "Incorrect message text"
        session = domain.session.SetQuantity(sku='Z019FDA9EAE0889BA47A1Z-1', qty=0).execute()
        assert session.total_items == 0, "Incorrect item total in cart"
        for message in session.messages:
            assert message.type != 'popup', "No limits are violated"
        session = domain.session.SetQuantity(sku='Z019FDA9EAE0889BA47A1Z-1', qty=13).execute()
        assert session.total_items == 12, "Incorrect item total in cart"
        assert len(session.messages), "limits are violated"
        assert session.messages[-1].type == 'popup', "Incorrect message type"
        assert 'stock' in session.messages[-1].text, "Incorrect message text"
        domain.session.RemoveItem(sku='Z019FDA9EAE0889BA47A1Z-1').execute()


def test_create_new_session_with_no_fleet():
    def mocked_estimate(wh_code):
        return {'is_shutdown': True, 'is_online': False, 'shutdown_time': None, 'open_time': None, 'load_factor': None}

    with Context.service(visitor_id="v1", customer_code="c1", lat=WH2_LAT, lng=WH2_LNG, address_key='A091-1'):
        domain.session.deactivate_session(SessionOwnerType.CUSTOMER, 'c1')
        domain.session.deactivate_session(SessionOwnerType.GUEST, 'v1')
        session = domain.session.GetOrCreate().execute()


def test_session_default_payment_cod(data_order):
    with Context.service(visitor_id="v1", customer_code="c1", lat=WH2_LAT, lng=WH2_LNG, address_key='A091-1'):
        session, order_nr = testutil.place_order(items=[('Z019FDA9EAE0889BA47A1Z-1', 1)], payment_method_code='cod')
    process_all_events()
    with Context.service(visitor_id="v1", customer_code="c1", lat=WH2_LAT, lng=WH2_LNG):
        _ = domain.session.AddItem(sku='Z019FDA9EAE0889BA47A1Z-1', qty=13).execute()
        new_session = domain.session.RemoveItem(sku='Z019FDA9EAE0889BA47A1Z-1').execute()
    assert session.payment_method_code != new_session.payment_method_code, 'Default method should not be saved for cod'


def test_session_default_payment_cc(data_order):
    with Context.service(visitor_id="v1", customer_code="c1", lat=WH2_LAT, lng=WH2_LNG, address_key='A091-1'):
        session, order_nr = testutil.place_order(
            items=[('Z019FDA9EAE0889BA47A1Z-1', 1)],
            payment_method_code='cc_noonpay',
            payment_token='4500000392',
            credit_card_mask='mask',
        )
    process_all_events()
    payment_mock = get_payment_mock(authorized_amount=12.65, status='payment_captured')
    with mock.patch('libexternal.Payment', new_callable=payment_mock) as _:
        with Context.service(customer_code="c1"):
            domain.payment.payment_updated(order_nr)
            # instead of calling this - we can have a separate function for tests which gets all columns for an order
    process_all_events()
    with Context.service(visitor_id="v1", customer_code="c1", lat=WH2_LAT, lng=WH2_LNG):
        _ = domain.session.AddItem(sku='Z019FDA9EAE0889BA47A1Z-1', qty=13).execute()
        new_session = domain.session.RemoveItem(sku='Z019FDA9EAE0889BA47A1Z-1').execute()
    assert session.payment_method_code == new_session.payment_method_code, 'Default method not saved'
    assert session.payment_token == new_session.payment_token, 'Default method not saved'


def test_session_default_payment_credit(data_order):
    with Context.service(visitor_id="v1", customer_code="c1", lat=WH2_LAT, lng=WH2_LNG, address_key='A091-1'):
        session, order_nr = testutil.place_order(
            items=[('Z019FDA9EAE0889BA47A1Z-1', 1)], payment_method_code='nopayment', credit_amount=D(12.65)
        )
    process_all_events()
    payment_mock = get_payment_mock(authorized_amount=12.65, status='payment_captured')
    with mock.patch('libexternal.Payment', new_callable=payment_mock) as _:
        with Context.service(customer_code="c1"):
            domain.payment.payment_updated(order_nr)
            # instead of calling this - we can have a separate function for tests which gets all columns for an order
    process_all_events()
    with Context.service(visitor_id="v1", customer_code="c1", lat=WH2_LAT, lng=WH2_LNG):
        _ = domain.session.AddItem(sku='Z019FDA9EAE0889BA47A1Z-1', qty=13).execute()
        new_session = domain.session.RemoveItem(sku='Z019FDA9EAE0889BA47A1Z-1').execute()
    assert new_session.payment_method_code != 'nopayment', 'Default method should not be saved for credit'


def process_all_events():
    from liborder.domain.boilerplate_event import ActionCode
    from liborder.domain.order import order_shipment_created, order_ready_for_pickup, update_default_payment_method
    from liborder.domain.payment import payment_order_create, capture_payment_amount


    from apporder.workers.order import event_processor

    event_processor(action_code=ActionCode.ORDER_SHIPMENT_CREATED)(order_shipment_created)()
    event_processor(action_code=ActionCode.ORDER_READY_FOR_PICKUP)(order_ready_for_pickup)()
    event_processor(action_code=ActionCode.PAYMENT_ORDER_CREATE)(payment_order_create)()
    event_processor(action_code=ActionCode.PAYMENT_ORDER_CAPTURE)(capture_payment_amount)()
    event_processor(action_code=ActionCode.DEFAULT_PAYMENT_UPDATE)(update_default_payment_method)()
