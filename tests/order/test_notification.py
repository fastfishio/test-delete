import json
import uuid
from unittest import mock

import libexternal
from libexternal import customer
from liborder import Context, domain, ctx
from liborder.domain.enums import Status, OrderPayer, PaymentMethod
from liborder.domain.boilerplate_event import ActionCode, create_event
from liborder.domain.notification import notification_order_update
from liborder.domain.order import add_shipment
from liborder.domain.payment import payment_order_create
from libutil import util
from tests.order import util as testutil
from tests.order.mocks import customer as mocked_customer
from tests.order.mocks.notification import NotificationMock
from tests.order.mocks.payment import get_payment_mock

WH2_LAT = 252005240
WH2_LNG = 552807372
WH3_LAT = 252105240
WH3_LNG = 552817372


def test_notification_postpaid(monkeypatch, data_order):
    monkeypatch.setattr(customer, 'get_customer_address', mocked_customer.get_customer_address)

    notification_svc = NotificationMock()
    monkeypatch.setattr(libexternal.notification.NotificationList, 'send',
                        NotificationMock.send_mock(notification_svc))

    with Context.service(visitor_id="v1", customer_code="c1", lat=WH2_LAT, lng=WH2_LNG, address_key='A091-1'):
        _, order_nr = testutil.place_order(items=[('Z019FDA9EAE0889BA47A1Z-1', 1)], payment_method_code='cod')

    notifs = notification_svc.get_last_call()
    assert notification_svc.no_of_calls() == 1
    assert len(notifs) == 1

    notif = notifs[0]
    assert notif['policy_name'] == 'default'
    assert notif['template_name'] == 'order_confirmed'
    assert notif['channel_code'] == 'push'
    assert notif['to']['recipient'] == 'c1'
    assert notif['payload']['order_nr'] == order_nr
    assert notif['idempotency_key'] == f'order_confirmed-push-{order_nr}'


def test_notification_prepaid(monkeypatch, app_order):
    notification_svc = NotificationMock()
    monkeypatch.setattr(libexternal.notification.NotificationList, 'send',
                        NotificationMock.send_mock(notification_svc))

    with Context.service(visitor_id="v1", customer_code="c1", lat=WH2_LAT, lng=WH2_LNG, address_key='A091-1'):
        session, order_nr = testutil.place_order(items=[('Z019FDA9EAE0889BA47A1Z-1', 1)], payment_token='4500000392',
                                                 payment_method_code='cc_noonpay')
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

    notifications = notification_svc.get_last_call_template()
    assert notification_svc.no_of_calls() == 1
    assert notifications == ['boilerplate_push_order_confirmed']


def test_notification_logistics(monkeypatch):
    from libutil.util import equal_decimals
    from libcs.domain import customer_service

    notification_svc = NotificationMock()
    monkeypatch.setattr(libexternal.notification.NotificationList, 'send',
                        NotificationMock.send_mock(notification_svc))

    with Context.service(visitor_id="v1", customer_code="c1", lat=WH2_LAT, lng=WH2_LNG, address_key='A091-1'):
        _, order_nr = testutil.place_order(items=[('Z019FDA9EAE0889BA47A1Z-1', 1)],
                                           payment_method_code='cod')

    process_all_events()
    notifications = notification_svc.get_last_call_template()
    assert notifications == ['boilerplate_push_order_confirmed']
    assert notification_svc.no_of_calls() == 1

    # TODO: OMS-shipment logic, perhaps remove on logistics cleanup
    # with Context.service():
    #     awb_nr = mocked_oms.mock_shipment(order_nr, num_items=1)
    # process_all_events()
    # assert notification_svc.no_of_calls() == 1
    #
    # shipment_items = oms.get_shipment_details(awb_nr)
    # assert len(shipment_items) == 1, "Incorrect number of items in shipment"
    #
    # with Context.service(customer_code='c1'):
    #     #  to update order status: @farouk should this be handled by event processors directly?
    #     domain.order.modify_order(order_nr, {})
    #
    #     internal_order = domain.order.GetDetails(order_nr=order_nr).execute(internal=True, formatted=False)
    #     order_history = json.loads(internal_order['order_status_history'])
    #     assert len(order_history.keys()) == 3, "Only two statuses should exist in history"
    #     assert 'confirmed' in order_history, "confirmed status should be in history"
    #     assert 'ready_for_pickup' in order_history, "ready_for_pickup status should be in history"
    #     assert 'picked_up' in order_history, "picked_up status should be in history"
    #     assert order_history['confirmed'] <= order_history['ready_for_pickup'], "confirmed status must come first"
    #
    # process_all_events()
    # notifications = notification_svc.get_last_call_template()
    # assert notification_svc.no_of_calls() == 2
    # assert notifications == ['boilerplate_push_order_picked_up']
    #
    # with Context.service():
    #     mocked_logistics.delivered(order_nr=order_nr)
    #
    # with Context.service(customer_code='c1'):
    #     #  to update order status: @farouk should this be handled by event processors directly?
    #     domain.order.modify_order(order_nr, {})
    #
    #     order_details = domain.order.GetDetails(order_nr=order_nr).execute(internal=True)
    #     assert order_details.status_code == "delivered"
    #
    # process_all_events()
    # notifs = notification_svc.get_last_call()
    # assert notification_svc.no_of_calls() == 3
    # assert len(notifs) == 2
    #
    # notif = notifs[0]
    # assert notif['template_name'] == 'order_delivered'
    # assert notif['idempotency_key'] == f'order_delivered-push-{order_nr}'
    # assert notif['to']['recipient'] == 'c1'
    # assert notif['payload']['order_nr'] == order_nr
    #
    # notif = notifs[1]
    # assert notif['template_name'] == 'order_delivered'
    # assert notif['idempotency_key'] == f'order_delivered-email-{order_nr}'
    # assert notif['to']['recipient'] == 'example@domain.com'
    # assert notif['payload']['order_nr'] == order_nr


def process_all_events():
    from liborder.domain.order import order_shipment_created, order_ready_for_pickup
    from apporder.workers.order import event_processor
    event_processor(action_code=ActionCode.ORDER_SHIPMENT_CREATED)(order_shipment_created)()
    event_processor(action_code=ActionCode.ORDER_READY_FOR_PICKUP)(order_ready_for_pickup)()
    event_processor(action_code=ActionCode.NOTIFICATION_ORDER_UPDATE)(notification_order_update)()


def test_notif_checkout_credit_and_cc_failed_then_place_order_again(monkeypatch):
    from decimal import Decimal as D

    notification_svc = NotificationMock()
    monkeypatch.setattr(libexternal.notification.NotificationList, 'send',
                        NotificationMock.send_mock(notification_svc))

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

    notifs = notification_svc.get_last_call()
    assert notification_svc.no_of_calls() == 1
    assert len(notifs) == 1

    notif = notifs[0]
    assert notif['template_name'] == 'order_failed'
    assert notif['idempotency_key'] == f'order_failed-push-{order_nr}'
    assert notif['to']['recipient'] == 'c1'
    assert notif['payload']['order_nr'] == order_nr
    assert notif['payload']['fail_reason'] == 'payment failed'

    with Context.service(visitor_id="v1", customer_code="c1", lat=WH2_LAT, lng=WH2_LNG):
        domain.session.RemoveItem(sku='Z019FDA9EAE0889BA47A1Z-1').execute()


def test_notif_one_incomplete_shipment(monkeypatch):
    from libutil.util import equal_decimals
    from libcs.domain import customer_service

    notification_svc = NotificationMock()
    monkeypatch.setattr(libexternal.notification.NotificationList, 'send',
                        NotificationMock.send_mock(notification_svc))

    with Context.service(visitor_id="v1", customer_code="c1", lat=WH2_LAT, lng=WH2_LNG, address_key='A091-1'):
        _, order_nr = testutil.place_order(items=[('Z019FDA9EAE0889BA47A1Z-1', 3)], payment_method_code='cod')

    process_all_events()
    assert notification_svc.no_of_calls() == 1

    # TODO: OMS-shipment logic, perhaps remove on logistics cleanup
    # with Context.service():
    #     awb_nr = mocked_oms.mock_shipment(order_nr, num_items=1)
    # process_all_events()
    # shipment_items = oms.get_shipment_details(awb_nr)
    # assert len(shipment_items) == 1, "Incorrect number of items in shipment"
    #
    # notifs = notification_svc.get_last_call()
    # assert notification_svc.no_of_calls() == 2
    # assert len(notifs) == 2
    #
    # notif = notifs[0]
    # assert notif['template_name'] == 'order_partial'
    # assert notif['idempotency_key'] == f'order_partial-push-{order_nr}'
    # assert notif['to']['recipient'] == 'c1'
    # assert notif['payload']['order_nr'] == order_nr
    #
    # notif = notifs[1]
    # assert notif['template_name'] == 'order_partial'
    # assert notif['idempotency_key'] == f'order_partial-email-{order_nr}'
    # assert notif['to']['recipient'] == 'example@domain.com'
    # assert notif['payload']['order_nr'] == order_nr
    # assert len(notif['payload']['cancelled_items']) == 2
    # # print(notif['payload']['canceled_items'])
    #
    # with Context.service(customer_code='c1'):
    #     #  to update order status: @farouk should this be handled by event processors directly?
    #     domain.order.modify_order(order_nr, {})
    #
    # notifs = notification_svc.get_last_call()
    # assert notification_svc.no_of_calls() == 3
    # assert len(notifs) == 1
    #
    # notif = notifs[0]
    # assert notif['template_name'] == 'order_picked_up'
    # assert notif['idempotency_key'] == f'order_picked_up-push-{order_nr}'
    # assert notif['to']['recipient'] == 'c1'
    # assert notif['payload']['order_nr'] == order_nr


def test_notif_no_shipment(monkeypatch):
    notification_svc = NotificationMock()
    monkeypatch.setattr(libexternal.notification.NotificationList, 'send',
                        NotificationMock.send_mock(notification_svc))

    with Context.service(visitor_id="v1", customer_code="c1", lat=WH2_LAT, lng=WH2_LNG, address_key='A091-1'):
        _, order_nr = testutil.place_order(items=[('Z019FDA9EAE0889BA47A1Z-1', 3)], payment_method_code='cod')
        domain.order.cancel_order_with_no_shipments({'data': {'order_nr': order_nr}})

    notifs = notification_svc.get_last_call()
    assert notification_svc.no_of_calls() == 2
    assert len(notifs) == 1

    notif = notifs[0]
    assert notif['template_name'] == 'order_cancelled'
    assert notif['idempotency_key'] == f'order_cancelled-push-{order_nr}'
    assert notif['to']['recipient'] == 'c1'
    assert notif['payload']['order_nr'] == order_nr
    assert notif['payload']['cancel_reason'] == 'all items are out of stock'


def test_notif_undelivered(monkeypatch):
    notification_svc = NotificationMock()
    monkeypatch.setattr(libexternal.notification.NotificationList, 'send',
                        NotificationMock.send_mock(notification_svc))

    with Context.service(visitor_id="v1", customer_code="c1", lat=WH2_LAT, lng=WH2_LNG, address_key='A091-1'):
        _, order_nr = testutil.place_order(items=[('Z019FDA9EAE0889BA47A1Z-1', 1)], payment_method_code='cod')

    assert notification_svc.get_last_call_template() == ['boilerplate_push_order_confirmed']
    assert notification_svc.no_of_calls() == 1

    # This is naive, it should be changed later with a flow
    with Context.service():
        from jsql import sql
        sql(ctx.conn, '''
            UPDATE sales_order
            SET status_code_order = :status_code
            WHERE order_nr = :order_nr
        ''', order_nr=order_nr, status_code=Status.UNDELIVERED.value)

        create_event(ActionCode.NOTIFICATION_ORDER_UPDATE, {'order_nr': order_nr})

    notifs = notification_svc.get_last_call()
    assert notification_svc.no_of_calls() == 2

    notif = notifs[0]
    assert notif['template_name'] == 'order_undelivered'
    assert notif['idempotency_key'] == f'order_undelivered-push-{order_nr}'
    assert notif['to']['recipient'] == 'c1'
    assert notif['payload']['order_nr'] == order_nr

    notif = notifs[1]
    assert notif['template_name'] == 'order_undelivered'
    assert notif['idempotency_key'] == f'order_undelivered-email-{order_nr}'
    assert notif['to']['recipient'] == 'example@domain.com'
    assert notif['payload']['order_nr'] == order_nr
