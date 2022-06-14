from unittest import mock
from unittest.mock import MagicMock

from jsql import sql

from liborder import Context, domain, ctx
from liborder.domain.enums import Status, PaymentMethod, OrderPayer
from liborder.domain.boilerplate_event import ActionCode
from liborder.domain.order import cancel_order
from liborder.domain.payment import payment_order_create
from libutil import util
from tests.order import util as testutil
from tests.order.mocks.payment import get_payment_mock

WH2_LAT = 252005240
WH2_LNG = 552807372
WH3_LAT = 252105240
WH3_LNG = 552817372


def test_order_cancelation_credit_only(monkeypatch, data_order):
    # todo: not everything should be inside Context here
    with Context.service(visitor_id="v1", customer_code="c1", lat=WH2_LAT, lng=WH2_LNG, address_key='A091-1'):
        session, order_nr = testutil.place_order(items=[('Z019FDA9EAE0889BA47A1Z-1', 1)],
                                           payment_method_code='nopayment', credit_amount=12.65)
    with Context.service():
        order_details = domain.order.GetDetails(order_nr=order_nr).execute(internal=True)
        assert order_details.country_code == 'AE'
        assert order_details.status_code == Status.PENDING.value
        assert order_details.status_code_payment == Status.PENDING.value
        assert order_details.order_total == session.order_total

    with Context.service():
        # improve this a bit
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

    # order canceled
    with Context.service():
        cancel_order(order_nr=order_nr)
        order_details = domain.order.GetDetails(order_nr=order_nr).execute(internal=True)
    assert order_details.status_code == Status.CANCELLED.value
    assert order_details.order_payer_code == OrderPayer.NONE.value
    assert util.equal_decimals(order_details['order_collect_from_customer'], 0)
    assert util.equal_decimals(order_details['order_collected_from_customer'], 12.65)

    # now, settle payment should kick in and refund the credit amount
    with Context.service():
        domain.payment.settle_payment(order_nr)

    order_details = testutil.get_order_details(order_nr)
    assert util.equal_decimals(order_details['order_collect_from_customer'], 0)
    assert util.equal_decimals(order_details['order_collected_from_customer'], 0)
    assert util.equal_decimals(order_details['order_credit_captured'], 0)


def test_order_cancelation_credit_and_cc(monkeypatch, data_order):
    # todo: not everything should be inside Context here
    with Context.service(visitor_id="v1", customer_code="c1", lat=WH2_LAT, lng=WH2_LNG, address_key='A091-1'):
        session, order_nr = testutil.place_order(items=[('Z019FDA9EAE0889BA47A1Z-1', 1)], payment_token='4500000392',
                                                 payment_method_code='cc_noonpay', credit_amount=10.00)
    with Context.service():
        order_details = domain.order.GetDetails(order_nr=order_nr).execute(internal=True)
        assert order_details.status_code == Status.PENDING.value
        assert order_details.status_code_payment == Status.PENDING.value
        assert order_details.order_total == session.order_total

    process_all_events()

    payment_mock = get_payment_mock(authorized_amount=2.65)
    with mock.patch('libexternal.Payment', new_callable=payment_mock) as _:
        with Context.service():
            domain.payment.payment_updated(order_nr)
    order_details = testutil.get_order_details(order_nr)
    assert order_details['payment_intent_token']
    assert order_details['status_code_payment'] == Status.DONE.value
    assert order_details['status_code_order'] == Status.CONFIRMED.value
    assert util.equal_decimals(order_details['order_payment_authorized'], 2.65)
    assert util.equal_decimals(order_details['order_credit_amount'], -10.00)
    assert util.equal_decimals(order_details['order_credit_captured'], -10.00)

    # order canceled
    with Context.service():
        cancel_order(order_nr=order_nr)
        order_details = domain.order.GetDetails(order_nr=order_nr).execute(internal=True)
    assert order_details.status_code == Status.CANCELLED.value
    assert order_details.order_payer_code == OrderPayer.NONE.value
    assert util.equal_decimals(order_details['order_collect_from_customer'], 0)
    assert util.equal_decimals(order_details['order_collected_from_customer'], 10.00)

    # this will reverse credit captured
    with Context.service():
        domain.payment.settle_payment(order_nr)

    # this will reverse cc payment
    from unittest.mock import MagicMock
    pm = payment_mock
    pm.reverse = MagicMock()
    with mock.patch('libexternal.Payment', new_callable=payment_mock) as _:
        with Context.service():
            domain.order.order_cancel_authorized()
    # here we verify if Payment.reverse was actually called or not
    pm.reverse.assert_called()

    # now, since payment was reversed, we let the mock return the reversed payment
    payment_mock = get_payment_mock(authorized_amount=2.65, reversed_amount=2.65)
    with mock.patch('libexternal.Payment', new_callable=payment_mock) as _:
        with Context.service(customer_code="c1"):
            domain.payment.payment_updated(order_nr)

    order_details = testutil.get_order_details(order_nr)
    assert util.equal_decimals(order_details['order_collect_from_customer'], 0)
    assert util.equal_decimals(order_details['order_collected_from_customer'], 0)
    assert util.equal_decimals(order_details['order_credit_captured'], 0)
    # authorized is 0 because we calculate authorized as: authorized_amount - reversed_amount - captured_amount
    assert util.equal_decimals(order_details['order_payment_authorized'], 0)
    assert util.equal_decimals(order_details['order_payment_refunded'], 0)


def test_order_cancelation_cc(monkeypatch, data_order):
    # todo: not everything should be inside Context here
    with Context.service(visitor_id="v1", customer_code="c1", lat=WH2_LAT, lng=WH2_LNG, address_key='A091-1'):
        session, order_nr = testutil.place_order(items=[('Z019FDA9EAE0889BA47A1Z-1', 1)], payment_token='4500000392',
                                                 payment_method_code='cc_noonpay')
        order_details = domain.order.GetDetails(order_nr=order_nr).execute(internal=True)
        assert util.equal_decimals(order_details.order_payment_amount, 12.65)
        assert order_details.status_code == Status.PENDING.value
        assert order_details.status_code_payment == Status.PENDING.value
        assert order_details.payment_method_code == PaymentMethod.CC_NOONPAY.value
        assert order_details.order_credit_amount == 0
        assert order_details.order_total == session.order_total

    process_all_events()
    payment_mock = get_payment_mock(authorized_amount=12.65)
    with mock.patch('libexternal.Payment', new_callable=payment_mock) as _:
        with Context.service():
            domain.payment.payment_updated(order_nr)

    order_details = testutil.get_order_details(order_nr)
    assert order_details['payment_intent_token']
    assert order_details['status_code_payment'] == Status.DONE.value
    assert order_details['status_code_order'] == Status.CONFIRMED.value
    assert util.equal_decimals(order_details['order_payment_authorized'], 12.65)
    assert util.equal_decimals(order_details['order_credit_captured'], 0.00)

    # order canceled
    with Context.service():
        cancel_order(order_nr=order_nr)
        order_details = domain.order.GetDetails(order_nr=order_nr).execute(internal=True)
    assert order_details.status_code == Status.CANCELLED.value
    assert order_details.order_payer_code == OrderPayer.NONE.value
    assert util.equal_decimals(order_details['order_collect_from_customer'], 0)
    # amount is just authorized as of now, so collected from customer is still 0
    assert util.equal_decimals(order_details['order_collected_from_customer'], 0)
    assert util.equal_decimals(order_details['order_payment_authorized'], 12.65)
    assert util.equal_decimals(order_details['order_payment_captured'], 0)

    # this will reverse cc payment
    pm = payment_mock
    pm.reverse = MagicMock()
    with mock.patch('libexternal.Payment', new_callable=payment_mock) as _:
        with Context.service():
            domain.order.order_cancel_authorized()
    # here we verify if Payment.reverse was actually called or not
    pm.reverse.assert_called()
    # now, since payment was reversed, we let the mock return the reversed payment
    payment_mock = get_payment_mock(authorized_amount=2.65, reversed_amount=2.65)
    with mock.patch('libexternal.Payment', new_callable=payment_mock) as _:
        with Context.service(customer_code="c1"):
            domain.payment.payment_updated(order_nr)
    order_details = testutil.get_order_details(order_nr)
    assert util.equal_decimals(order_details['order_collect_from_customer'], 0)
    assert util.equal_decimals(order_details['order_collected_from_customer'], 0)
    assert util.equal_decimals(order_details['order_credit_captured'], 0)
    # authorized is 0 because we calculate authorized as: authorized_amount - reversed_amount - captured_amount
    assert util.equal_decimals(order_details['order_payment_authorized'], 0)
    assert util.equal_decimals(order_details['order_payment_refunded'], 0)


def test_refund_oos_items(monkeypatch, data_order):
    # todo: not everything should be inside Context here
    with Context.service(visitor_id="v1", customer_code="c1", lat=WH2_LAT, lng=WH2_LNG, address_key='A091-1'):
        session, order_nr = testutil.place_order(items=[('Z019FDA9EAE0889BA47A1Z-1', 2)], payment_token='4500000392',
                                                 payment_method_code='cc_noonpay')
        order_details = domain.order.GetDetails(order_nr=order_nr).execute(internal=True)
    assert order_details.country_code == 'AE'
    assert util.equal_decimals(order_details.order_payment_amount, 15.3)
    assert order_details.status_code == Status.PENDING.value
    assert order_details.status_code_payment == Status.PENDING.value
    assert order_details.payment_method_code == PaymentMethod.CC_NOONPAY.value
    assert order_details.order_credit_amount == 0
    assert order_details.order_total == session.order_total

    process_all_events()
    payment_mock = get_payment_mock(authorized_amount=15.3)

    with mock.patch('libexternal.Payment', new_callable=payment_mock) as _:
        with Context.service():
            domain.payment.payment_updated(order_nr)
            order_details = domain.order.GetDetails(order_nr=order_nr).execute(internal=True)
    assert order_details['payment_intent_token']
    assert order_details["status_code_payment"] == Status.DONE.value
    assert order_details["status_code"] == Status.CONFIRMED.value
    assert util.equal_decimals(order_details["order_payment_authorized"], 15.3)
    process_all_events()

    ''' below assert may be an overkill, but i wanted to have it'''
    pm = payment_mock
    pm.capture = MagicMock()
    with mock.patch('libexternal.Payment', new_callable=payment_mock) as _:
        # with the below, PAYMENT_ORDER_CAPTURE event should be processed
        process_all_events()
    mock_calls = pm.capture.mock_calls

    # TODO: used to do mock shipment here, to adjust
    # assert len(mock_calls) == 1
    # we need to verify if capture was called with the right amount
    #  sorry, the below line is messy - but to verify if a call was made with "decimal" argument - i found only this way
    #  because of precision issue in doing:
    #  pm.capture.assert_called_with(order_nr, D(2.65))
    # assert util.equal_decimals(mock_calls[0][1][1], 2.65)

    payment_mock = get_payment_mock(authorized_amount=15.3, captured_amount=2.65)
    with mock.patch('libexternal.Payment', new_callable=payment_mock) as _:
        with Context.service():
            domain.payment.payment_updated(order_nr)
            order_details = domain.order.GetDetails(order_nr=order_nr).execute(internal=True)
    assert util.equal_decimals(order_details.order_payment_captured, 2.65)
    assert util.equal_decimals(order_details.order_payment_authorized, 12.65)

    # add adjustment
    #  should happen via api call ideally, but just YOLOing for the sake of the test scenario
    with Context.service():
        domain.order.modify_order(order_nr, {'order_mp_adjustment': -1}, internal=True)

    ''' below assert may be an overkill, but i wanted to have it'''
    payment_mock = get_payment_mock(authorized_amount=15.3, captured_amount=2.65)
    pm = payment_mock
    pm.refund = MagicMock()
    with mock.patch('libexternal.Payment', new_callable=payment_mock) as _:
        with Context.service():
            domain.payment.settle_payment(order_nr)
    mock_calls = pm.refund.mock_calls

    # TODO: used to do mock shipment here, to adjust
    # assert len(mock_calls) == 1
    # we need to verify if capture was called with the right amount
    #  sorry, the below line is messy - but to verify if a call was made with "decimal" argument - i found only this way
    #  because of precision issue in doing:
    #  pm.capture.assert_called_with(order_nr, D(1))
    # assert util.equal_decimals(mock_calls[0][1][1], 1)

    # now say if settle_payment is called again
    ''' below assert may be an overkill, but i wanted to have it'''
    payment_mock = get_payment_mock(authorized_amount=15.3, captured_amount=2.65, refunded_amount=1)
    pm = payment_mock
    pm.refund = MagicMock()
    with mock.patch('libexternal.Payment', new_callable=payment_mock) as _:
        with Context.service():
            domain.payment.update_payment_info(order_nr)
            domain.payment.settle_payment(order_nr)
    mock_calls = pm.refund.mock_calls
    # there would be no calls to refund
    assert len(mock_calls) == 0


# todo: add below test cases
#  payment done - order confirmed - few items oos - capture appropriate amount - order canceled - refund captured amount


def process_all_events():
    from liborder.domain.order import order_shipment_created, order_ready_for_pickup
    from liborder.domain.payment import payment_order_create, capture_payment_amount

    from apporder.workers.order import event_processor
    event_processor(action_code=ActionCode.ORDER_SHIPMENT_CREATED)(order_shipment_created)()
    event_processor(action_code=ActionCode.ORDER_READY_FOR_PICKUP)(order_ready_for_pickup)()
    event_processor(action_code=ActionCode.PAYMENT_ORDER_CREATE)(payment_order_create)()
    event_processor(action_code=ActionCode.PAYMENT_ORDER_CAPTURE)(capture_payment_amount)()
