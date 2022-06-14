import datetime
from decimal import Decimal as D
from unittest import mock
import logging
import time
logger = logging.getLogger(__name__)
import pytest
import liborder
from liborder import Context, domain
from liborder.domain.enums import Status, PaymentMethod, OrderPayer
from liborder.domain.payment import payment_order_create
from libutil import util
from tests.order import util as testutil
from tests.order.mocks.payment import get_payment_mock
from tests.order.mocks.credit import NegativeMockCredit

WH2_LAT = 252005240
WH2_LNG = 552807372
WH3_LAT = 252105240
WH3_LNG = 552817372

assert liborder


def is_within_minutes(date, minutes, tolerance=1):
    now = datetime.datetime.now()
    start = now + datetime.timedelta(minutes=minutes) - datetime.timedelta(minutes=tolerance)
    end = now + datetime.timedelta(minutes=minutes) + datetime.timedelta(minutes=tolerance)

    return start <= date < end


def test_checkout(monkeypatch, data_order):
    # todo: not everything should be inside Context here
    with Context.service(visitor_id="v1", customer_code="c1", lat=WH2_LAT, lng=WH2_LNG, address_key='A091-1'):
        session, order_nr = testutil.place_order(items=[('Z019FDA9EAE0889BA47A1Z-1', 1)], payment_method_code='cod')
        session_code1 = session.session_code
        order_details = domain.order.GetDetails(order_nr=order_nr).execute()
        assert order_details.country_code == 'AE'
        assert order_details.status_code == "confirmed"
        assert order_details.order_total == session.order_total
        assert is_within_minutes(order_details.estimated_delivery_at, 15)
        # Try to get another session, should be a different session_code
        session = domain.session.GetOrCreate().execute()
        session_code2 = session.session_code
        assert session_code1 != session_code2, "Using an inactive session"


# todo: add following test cases
#  happy path prepaid payment
#  happy path credit amount covers the whole payment
#  credit amount exceeds the credits
#  prepaid + credit split
#  prepaid payment failed, credit should be refunded
#  authorized amount is 0
#  payment canceled -> order canceled
#  settlement to source/credit


def test_checkout_prepaid_happy(monkeypatch, app_order):
    with Context.service(visitor_id="v1", customer_code="c1", lat=WH2_LAT, lng=WH2_LNG, address_key='A091-1'):
        session, order_nr = testutil.place_order(items=[('Z019FDA9EAE0889BA47A1Z-1', 1)],
                                                 payment_method_code='cc_noonpay', payment_token='4500000392')
    with Context.service(visitor_id="v1", customer_code="c1", lat=WH2_LAT, lng=WH2_LNG):
        order_details = domain.order.GetDetails(order_nr=order_nr).execute(internal=True)
    assert order_details['order_payment_authorized'] == 0
    assert order_details['order_payment_captured'] == 0
    assert order_details['order_payment_refunded'] == 0
    assert order_details['status_code_payment'] == Status.PENDING.value
    assert order_details['status_code'] == Status.PENDING.value
    assert order_details['status_code_logistics'] == Status.NOT_SYNCED.value
    # payment intent should not have been created yet
    assert not order_details['payment_intent_token']

    # step 2: creating payment intent
    #  todo: improve this a bit
    with Context.service():
        payment_order_create({"data": {"order_nr": order_nr}})

    with Context.service(visitor_id="v1", customer_code="c1", lat=WH2_LAT, lng=WH2_LNG):
        order_details = domain.order.GetDetails(order_nr=order_nr).execute(internal=True)
    assert order_details['payment_intent_token']
    assert order_details['order_payment_authorized'] == 0
    assert order_details['order_payment_captured'] == 0
    assert order_details['order_payment_refunded'] == 0
    assert order_details['status_code_payment'] == Status.PENDING.value

    # step 3: authorize payment
    payment_mock = get_payment_mock(authorized_amount=12.65, status='payment_captured')
    with mock.patch('libexternal.Payment', new_callable=payment_mock) as _:
        with Context.service(customer_code="c1"):
            domain.payment.payment_updated(order_nr)
            # instead of calling this - we can have a separate function for tests which gets all columns for an order
            order_details = domain.order.GetDetails(order_nr=order_nr).execute(internal=True)

        assert order_details.country_code == 'AE'
        assert util.equal_decimals(order_details.order_payment_authorized, 12.65)
        # after payment status done (because amount is authorized) - order status should be updated
        assert order_details.status_code == Status.CONFIRMED.value
        assert order_details.status_code_payment == Status.DONE.value
        assert order_details.order_total == session.order_total


def test_checkout_credit_only(monkeypatch, app_order):
    with Context.service(visitor_id="v1", customer_code="c1", lat=WH2_LAT, lng=WH2_LNG, address_key='A091-1'):
        _, order_nr = testutil.place_order(items=[('Z019FDA9EAE0889BA47A1Z-1', 1)],
                                           payment_method_code='nopayment', credit_amount=D(12.65))
    with Context.service(visitor_id="v1", customer_code="c1", lat=WH2_LAT, lng=WH2_LNG):
        order_details = domain.order.GetDetails(order_nr=order_nr).execute(internal=True)
    assert order_details['order_payment_authorized'] == 0
    assert order_details['order_payment_captured'] == 0
    assert order_details['order_payment_refunded'] == 0
    assert util.equal_decimals(order_details['order_credit_amount'], -12.65)
    assert order_details['status_code_payment'] == Status.PENDING.value
    assert order_details['payment_method_code'] == PaymentMethod.NOPAYMENT.value
    assert order_details['status_code'] == Status.PENDING.value
    assert order_details['status_code_logistics'] == Status.NOT_SYNCED.value
    # payment intent should not have been created yet
    assert not order_details['payment_intent_token']

    # step 2: creating payment intent
    #  todo: improve this a bit
    with Context.service():
        payment_order_create({"data": {"order_nr": order_nr}})

    # in step2, credit amount should have been captured, so payment status should be done
    with Context.service(visitor_id="v1", customer_code="c1", lat=WH2_LAT, lng=WH2_LNG):
        order_details = domain.order.GetDetails(order_nr=order_nr).execute(internal=True)
    assert not order_details['payment_intent_token']
    assert order_details['order_payment_authorized'] == order_details['order_payment_captured'] == order_details[
        'order_payment_refunded'] == 0
    assert order_details['status_code_payment'] == Status.DONE.value
    assert order_details['status_code'] == Status.CONFIRMED.value
    assert util.equal_decimals(order_details['order_credit_amount'], -12.65)
    assert util.equal_decimals(order_details['order_credit_captured'], -12.65)


def test_checkout_credit_negative(monkeypatch):
    with Context.service(visitor_id="v1", customer_code="c1", lat=WH2_LAT, lng=WH2_LNG, address_key='A091-1'):
        _, order_nr = testutil.place_order(items=[('Z019FDA9EAE0889BA47A1Z-1', 1)],
                                           payment_method_code='nopayment', credit_amount=D(12.65))
    with Context.service(visitor_id="v1", customer_code="c1", lat=WH2_LAT, lng=WH2_LNG):
        order_details = domain.order.GetDetails(order_nr=order_nr).execute(internal=True)
    assert util.equal_decimals(order_details['order_credit_amount'], -12.65)
    assert order_details['status_code_payment'] == Status.PENDING.value
    assert order_details['payment_method_code'] == PaymentMethod.NOPAYMENT.value
    assert order_details['status_code'] == Status.PENDING.value

    # step 2: creating payment intent
    with pytest.raises(AssertionError, match='.*failed to capture credit amount*'):
        with mock.patch('libexternal.Credit', new_callable=NegativeMockCredit) as _:
            with Context.service():
                payment_order_create({"data": {"order_nr": order_nr}})

    # in step2, since credit amount has not been captured, payment and order status should stay pending
    with Context.service(visitor_id="v1", customer_code="c1", lat=WH2_LAT, lng=WH2_LNG):
        order_details = domain.order.GetDetails(order_nr=order_nr).execute(internal=True)
    # since there is no card payment - there should not be any payment intent
    assert not order_details['payment_intent_token']
    assert order_details['order_payment_authorized'] == order_details['order_payment_captured'] == order_details[
        'order_payment_refunded'] == 0
    assert order_details['status_code_payment'] == Status.PENDING.value
    assert order_details['status_code'] == Status.PENDING.value
    assert util.equal_decimals(order_details['order_credit_amount'], -12.65)
    assert util.equal_decimals(order_details['order_credit_captured'], 0)

    # after this, mark_payment_timeout_canceled should kick in and then payment status should be canceled
    # todo: process mark_payment_timeout_canceled and assert on statuses


def test_checkout_prepaid_and_credit(monkeypatch):
    with Context.service(visitor_id="v1", customer_code="c1", lat=WH2_LAT, lng=WH2_LNG, address_key='A091-1'):
        _, order_nr = testutil.place_order(items=[('Z019FDA9EAE0889BA47A1Z-1', 1)], payment_token='4500000392',
                                           payment_method_code='cc_noonpay', credit_amount=D(10.00))
    with Context.service(visitor_id="v1", customer_code="c1", lat=WH2_LAT, lng=WH2_LNG):
        order_details = domain.order.GetDetails(order_nr=order_nr).execute(internal=True)
    assert util.equal_decimals(order_details['order_credit_amount'], -10.00)
    assert order_details['status_code_payment'] == Status.PENDING.value
    assert order_details['payment_method_code'] == PaymentMethod.CC_NOONPAY.value
    assert util.equal_decimals(order_details['order_payment_amount'], D(2.65))
    assert order_details['status_code'] == Status.PENDING.value

    # step 2: creating payment intent
    #  todo: improve this a bit
    with Context.service():
        payment_order_create({"data": {"order_nr": order_nr}})

    with Context.service(visitor_id="v1", customer_code="c1", lat=WH2_LAT, lng=WH2_LNG):
        order_details = domain.order.GetDetails(order_nr=order_nr).execute(internal=True)
    # since there is no card payment - there should not be any payment intent
    assert order_details['payment_intent_token']
    assert order_details['order_payment_authorized'] == order_details['order_payment_captured'] == order_details[
        'order_payment_refunded'] == 0
    assert order_details['status_code_payment'] == Status.PENDING.value
    assert order_details['status_code'] == Status.PENDING.value
    assert util.equal_decimals(order_details['order_credit_amount'], -10.0)
    assert util.equal_decimals(order_details['order_credit_captured'], -10.0)

    # todo: add payment mock for authorized and captured


def test_checkout_credit_and_cod(monkeypatch):
    with Context.service(visitor_id="v1", customer_code="c1", lat=WH2_LAT, lng=WH2_LNG, address_key='A091-1'):
        _, order_nr = testutil.place_order(items=[('Z019FDA9EAE0889BA47A1Z-1', 1)],
                                           payment_method_code='cod', credit_amount=D(10.00))
    with Context.service(visitor_id="v1", customer_code="c1", lat=WH2_LAT, lng=WH2_LNG):
        order_details = domain.order.GetDetails(order_nr=order_nr).execute(internal=True)
    assert util.equal_decimals(order_details['order_credit_amount'], -10.00)
    assert order_details['status_code_payment'] == Status.PENDING.value
    assert order_details['payment_method_code'] == PaymentMethod.COD.value
    assert util.equal_decimals(order_details['order_payment_amount'], 2.65)
    assert util.equal_decimals(order_details['order_payment_cash_amount'], 2.65)
    assert order_details['status_code'] == Status.PENDING.value

    # step 2: creating payment intent
    #  todo: improve this a bit
    with Context.service():
        payment_order_create({"data": {"order_nr": order_nr}})

    with Context.service(visitor_id="v1", customer_code="c1", lat=WH2_LAT, lng=WH2_LNG):
        order_details = domain.order.GetDetails(order_nr=order_nr).execute(internal=True)
    # since there is no card payment - there should not be any payment intent
    assert not order_details['payment_intent_token']
    assert order_details['order_payment_authorized'] == order_details['order_payment_captured'] == order_details[
        'order_payment_refunded'] == 0
    # credit amount should have been captured now, so status should be done
    assert order_details['status_code_payment'] == Status.DONE.value
    assert order_details['status_code'] == Status.CONFIRMED.value
    assert util.equal_decimals(order_details['order_credit_amount'], -10.00)
    assert util.equal_decimals(order_details['order_credit_captured'], -10.00)
    assert util.equal_decimals(order_details['order_payment_cash_amount'], 2.65)


def test_checkout_credit_and_cc_failed_then_place_order_again(monkeypatch):
    with Context.service(visitor_id="v1", customer_code="c1", lat=WH2_LAT, lng=WH2_LNG, address_key='A091-1'):
        _, order_nr = testutil.place_order(items=[('Z019FDA9EAE0889BA47A1Z-1', 1)], payment_token='4500000392',
                                           payment_method_code='cc_noonpay', credit_amount=D(10.00))
    with Context.service(visitor_id="v1", customer_code="c1", lat=WH2_LAT, lng=WH2_LNG):
        order_details = domain.order.GetDetails(order_nr=order_nr).execute(internal=True)
    assert util.equal_decimals(order_details['order_credit_amount'], -10.00)
    assert order_details['status_code_payment'] == Status.PENDING.value
    assert order_details['payment_method_code'] == PaymentMethod.CC_NOONPAY.value
    assert util.equal_decimals(order_details['order_payment_amount'], 2.65)
    assert util.equal_decimals(order_details['order_payment_cash_amount'], 0)
    assert order_details['status_code'] == Status.PENDING.value

    # step 2: creating payment intent
    #  todo: improve this a bit
    with Context.service():
        payment_order_create({"data": {"order_nr": order_nr}})

    with Context.service(visitor_id="v1", customer_code="c1", lat=WH2_LAT, lng=WH2_LNG):
        order_details = domain.order.GetDetails(order_nr=order_nr).execute(internal=True)
    assert order_details['payment_intent_token']
    assert order_details['order_payment_authorized'] == order_details['order_payment_captured'] == order_details[
        'order_payment_refunded'] == 0
    # only credit amount has been captured, so status should still be PENDING
    assert order_details['status_code_payment'] == Status.PENDING.value
    assert order_details['status_code'] == Status.PENDING.value
    assert order_details['order_payer_code'] == OrderPayer.CUSTOMER.value
    assert util.equal_decimals(order_details['order_credit_amount'], -10.00)
    assert util.equal_decimals(order_details['order_credit_captured'], -10.00)
    assert util.equal_decimals(order_details['order_payment_cash_amount'], 0)

    # now - say the payment has failed
    payment_mock = get_payment_mock(status='payment_failed')
    with mock.patch('libexternal.Payment', new_callable=payment_mock) as _:
        with Context.service(customer_code="c1"):
            domain.payment.payment_updated(order_nr)
            order_details = domain.order.GetDetails(order_nr=order_nr).execute(internal=True)
    assert order_details['status_code_payment'] == Status.FAILED.value
    assert order_details['status_code'] == Status.FAILED.value
    assert order_details['order_payer_code'] == OrderPayer.NONE.value
    with Context.service():
        # now, after settle_payment is called, credit captured should be refunded back to the credit
        domain.payment.settle_payment(order_nr)
        order_details = domain.order.GetDetails(order_nr=order_nr).execute(internal=True)
    assert util.equal_decimals(order_details['order_credit_captured'], 0.00)
    assert util.equal_decimals(order_details['order_collect_from_customer'], 0.00)
    assert util.equal_decimals(order_details['order_collected_from_customer'], 0.00)
    # After payment fails, session should still have the cart items since no session was created afterwards
    with Context.service(visitor_id='v1', customer_code='c1', lat=WH2_LAT, lng=WH2_LNG, address_key='A091-1'):
        session = domain.session.GetOrCreate().execute()
        assert session.items, "session should have items"
        assert session.items[0].sku == 'Z019FDA9EAE0889BA47A1Z-1', "Incorrect SKU"
    # We should be able to place an order again with the same session
    with Context.service(visitor_id='v1', customer_code="c1", lat=WH2_LAT, lng=WH2_LNG, address_key='A091-1'):
        order_nr = domain.order.PlaceOrder(total=session.order_total).execute()['order_nr']
    with Context.service(visitor_id='v1', customer_code="c1", lat=WH2_LAT, lng=WH2_LNG):
        order = domain.order.GetDetails(order_nr=order_nr).execute(internal=True)
        assert order.order_total == session.order_total, "Invalid total"
        assert order.items[0].sku == 'Z019FDA9EAE0889BA47A1Z-1', "Invalid item in order"


def test_checkout_credit_and_cc_failed_then_add_items_to_new_session(monkeypatch):
    with Context.service(visitor_id="v1", customer_code="c1", lat=WH2_LAT, lng=WH2_LNG, address_key='A091-1'):
        _, order_nr = testutil.place_order(items=[('Z019FDA9EAE0889BA47A1Z-1', 1)], payment_token='4500000392',
                                           payment_method_code='cc_noonpay', credit_amount=D(10.00))
    with Context.service(visitor_id="v1", customer_code="c1", lat=WH2_LAT, lng=WH2_LNG):
        order_details = domain.order.GetDetails(order_nr=order_nr).execute(internal=True)
    assert util.equal_decimals(order_details['order_credit_amount'], -10.00)
    assert order_details['status_code_payment'] == Status.PENDING.value
    assert order_details['payment_method_code'] == PaymentMethod.CC_NOONPAY.value
    assert util.equal_decimals(order_details['order_payment_amount'], 2.65)
    assert util.equal_decimals(order_details['order_payment_cash_amount'], 0)
    assert order_details['status_code'] == Status.PENDING.value

    # step 2: creating payment intent
    #  todo: improve this a bit
    with Context.service():
        payment_order_create({"data": {"order_nr": order_nr}})

    with Context.service(visitor_id="v1", customer_code="c1", lat=WH2_LAT, lng=WH2_LNG):
        order_details = domain.order.GetDetails(order_nr=order_nr).execute(internal=True)
    assert order_details['payment_intent_token']
    assert order_details['order_payment_authorized'] == order_details['order_payment_captured'] == order_details[
        'order_payment_refunded'] == 0
    # only credit amount has been captured, so status should still be PENDING
    assert order_details['status_code_payment'] == Status.PENDING.value
    assert order_details['status_code'] == Status.PENDING.value
    assert order_details['order_payer_code'] == OrderPayer.CUSTOMER.value
    assert util.equal_decimals(order_details['order_credit_amount'], -10.00)
    assert util.equal_decimals(order_details['order_credit_captured'], -10.00)
    assert util.equal_decimals(order_details['order_payment_cash_amount'], 0)

    # Add to a new session before payment fails
    with Context.service(visitor_id='v1', customer_code='c1', lat=WH2_LAT, lng=WH2_LNG, address_key='A091-1'):
        new_session_code = domain.session.GetOrCreate().execute().session_code
        assert not new_session_code, "Must be a skeleton session"
        session = domain.session.AddItem(sku='Z019FDA9EAE0889BA47A1Z-1', qty=2).execute()
        new_session_code = session.session_code
        assert len(session.items) == 1, "session should 1 SKU"
        assert session.items[0].sku == 'Z019FDA9EAE0889BA47A1Z-1', "Incorrect SKU"
        assert session.items[0].qty == 2, "Incorrect qty"

    # now - say the payment has failed
    payment_mock = get_payment_mock(status='payment_failed')
    with mock.patch('libexternal.Payment', new_callable=payment_mock) as _:
        with Context.service(customer_code="c1"):
            domain.payment.payment_updated(order_nr)
            order_details = domain.order.GetDetails(order_nr=order_nr).execute(internal=True)
    assert order_details['status_code_payment'] == Status.FAILED.value
    assert order_details['status_code'] == Status.FAILED.value
    assert order_details['order_payer_code'] == OrderPayer.NONE.value
    with Context.service():
        # now, after settle_payment is called, credit captured should be refunded back to the credit
        domain.payment.settle_payment(order_nr)
        order_details = domain.order.GetDetails(order_nr=order_nr).execute(internal=True)
    assert util.equal_decimals(order_details['order_credit_captured'], 0.00)
    assert util.equal_decimals(order_details['order_collect_from_customer'], 0.00)
    assert util.equal_decimals(order_details['order_collected_from_customer'], 0.00)
    # Get session after payment failed, we should get the session that was created before the payment failed
    with Context.service(visitor_id='v1', customer_code='c1', lat=WH2_LAT, lng=WH2_LNG, address_key='A091-1'):
        session = domain.session.GetOrCreate().execute()
        session = domain.session.SetPaymentMethod(payment_method_code='cod').execute()
        assert len(session.items) == 1, "session should 1 SKU"
        assert session.items[0].sku == 'Z019FDA9EAE0889BA47A1Z-1', "Incorrect SKU"
        assert session.items[0].qty == 2, "Incorrect qty"
        assert session.session_code == new_session_code
    with Context.service(visitor_id='v1', customer_code="c1", lat=WH2_LAT, lng=WH2_LNG, address_key='A091-1'):
        order_nr = domain.order.PlaceOrder(total=session.order_total).execute()['order_nr']
    with Context.service(visitor_id='v1', customer_code="c1", lat=WH2_LAT, lng=WH2_LNG):
        order = domain.order.GetDetails(order_nr=order_nr).execute(internal=True)
        assert order.order_total == session.order_total, "Invalid total"
        assert order.items[0].sku == 'Z019FDA9EAE0889BA47A1Z-1', "Invalid item in order"
        assert order.items[1].sku == 'Z019FDA9EAE0889BA47A1Z-1', "Invalid item in order"


def test_order_listing(data_order):
    with Context.service(visitor_id="v1", customer_code="order_listing", lat=WH2_LAT, lng=WH2_LNG, address_key='A092-1'):
        _, order_nr_1 = testutil.place_order(items=[('Z019FDA9EAE0889BA47A1Z-1', 1)], payment_token='4500000392',
                                             payment_method_code='cc_noonpay', credit_amount=D(10.00))
    # Time machine doesn't work here as this is coming from DB default datetime
    time.sleep(1)
    with Context.service(visitor_id="v1", customer_code="order_listing", lat=WH2_LAT, lng=WH2_LNG, address_key='A092-1'):
        _, order_nr_2 = testutil.place_order(items=[('Z019FDA9EAE0889BA47A1Z-1', 1)], payment_token='4500000392',
                                             payment_method_code='cc_noonpay', credit_amount=D(10.00))

    with Context.service(visitor_id="v1", customer_code="order_listing", lat=WH2_LAT, lng=WH2_LNG, address_key='A092-1'):
        order_listing = domain.order.ListOrders(orders_per_page=2, page_nr=1).execute()
        assert order_listing.orders[0].order_nr == order_nr_2, 'Latest order should be first'
        assert order_listing.total_pages == 1, 'Incorrect total pages'

    with Context.service(visitor_id="v1", customer_code="order_listing", lat=WH2_LAT, lng=WH2_LNG, address_key='A092-1'):
        order_listing = domain.order.ListOrders(orders_per_page=1, page_nr=2).execute()
        assert order_listing.orders[0].order_nr == order_nr_1, 'Older order should be second'
        assert order_listing.total_pages == 2, 'Incorrect total pages'
    with Context.service(visitor_id="v1", customer_code="order_listing", lat=WH2_LAT, lng=WH2_LNG, address_key='A091-1'):
        order_listing = domain.order.ListOrders(orders_per_page=2, page_nr=1).execute()
        assert order_listing.orders[0].order_nr == order_nr_2, 'Latest order should be first'
        assert order_listing.orders[1].order_nr == order_nr_1, 'Older order should be second'
        assert order_listing.total_pages == 1, 'Incorrect total pages'
