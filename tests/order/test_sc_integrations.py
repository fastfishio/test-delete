import datetime
import json

from libcs.domain import customer_service
from liborder import Context, domain
from liborder.domain.boilerplate_event import ActionCode
from libutil.util import equal_decimals
from tests.order import util as testutil

WH2_LAT = 252005240
WH2_LNG = 552807372
WH3_LAT = 252105240
WH3_LNG = 552817372


def is_within_minutes(date, minutes, tolerance=1):
    now = datetime.datetime.now()
    start = now + datetime.timedelta(minutes=minutes) - datetime.timedelta(minutes=tolerance)
    end = now + datetime.timedelta(minutes=minutes) + datetime.timedelta(minutes=tolerance)

    return start <= date < end


def test_one_shipment_happy(monkeypatch):
    with Context.service(visitor_id="v1", customer_code="c1", lat=WH2_LAT, lng=WH2_LNG, address_key='A091-1'):
        session, order_nr = testutil.place_order(items=[('Z019FDA9EAE0889BA47A1Z-1', 1)], payment_method_code='cod')
    process_all_events()
    # TODO: adjust mock shipment OMS
    # with Context.service():
    #     awb_nr = mocked_oms.mock_shipment(order_nr, num_items=1)
    # process_all_events()
    # shipment_items = oms.get_shipment_details(awb_nr)
    # assert len(shipment_items) == 1, "Incorrect number of items in shipment"
    #
    # with Context.service():
    #     order_details = domain.order.GetDetails(order_nr=order_nr).execute(internal=True)
    #     assert order_details.status_code == "ready_for_pickup", "Incorrect order status"
    #     assert order_details.items[0].status_code == "confirmed", "Item should be confirmed"


def test_one_shipment_multi_item_happy(monkeypatch):
    with Context.service(visitor_id="v1", customer_code="c1", lat=WH2_LAT, lng=WH2_LNG, address_key='A091-1'):
        session, order_nr = testutil.place_order(items=[('Z019FDA9EAE0889BA47A1Z-1', 2)], payment_method_code='cod')
    process_all_events()

    # TODO: adjust shipment-oms mock
    # with Context.service():
    #     mocked_oms.mock_shipment(order_nr, num_items=2)
    # process_all_events()
    #
    # with Context.service():
    #     order_details = domain.order.GetDetails(order_nr=order_nr).execute(internal=True)
    #     assert order_details.status_code == "ready_for_pickup", "Incorrect order status"
    #     assert order_details.order_delivery_fee == 10, "Order is complete, shipping fee should be > 0"
    #     assert order_details.items[0].status_code == "confirmed", "Item should be confirmed"
    #     assert order_details.items[1].status_code == "confirmed", "Item should be confirmed"


def test_one_incomplete_shipment(monkeypatch):
    with Context.service(visitor_id="v1", customer_code="c1", lat=WH2_LAT, lng=WH2_LNG, address_key='A091-1'):
        session, order_nr = testutil.place_order(items=[('Z019FDA9EAE0889BA47A1Z-1', 2)], payment_method_code='cod')
    process_all_events()

    # TODO: adjust shipment-oms mock
    # with Context.service():
    #     awb_nr = mocked_oms.mock_shipment(order_nr, num_items=1)
    # process_all_events()
    # shipment_items = oms.get_shipment_details(awb_nr)
    # assert len(shipment_items) == 1, "Incorrect number of items in shipment"


def test_logistics_task_status(monkeypatch):
    with Context.service(visitor_id="v1", customer_code="c1", lat=WH2_LAT, lng=WH2_LNG, address_key='A091-1'):
        session, order_nr = testutil.place_order(items=[('Z019FDA9EAE0889BA47A1Z-1', 1)], payment_method_code='cod')
    process_all_events()

    # TODO: adjust shipment-oms mock
    # with Context.service():
    #     awb_nr = mocked_oms.mock_shipment(order_nr, num_items=1)
    # process_all_events()
    # shipment_items = oms.get_shipment_details(awb_nr)
    # assert len(shipment_items) == 1, "Incorrect number of items in shipment"
    #
    # with Context.service(customer_code='c1'):
    #     #  to update order status - should this be handled via events?
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
    # with Context.service():
    #     mocked_logistics.delivered(order_nr=order_nr)
    #
    # with Context.service(customer_code='c1'):
    #     #  to update order status - should this be handled via events?
    #     domain.order.modify_order(order_nr, {})
    #     internal_order = domain.order.GetDetails(order_nr=order_nr).execute(internal=True, formatted=False)
    #     order_history = json.loads(internal_order['order_status_history'])
    #     assert len(order_history.keys()) == 4, "Only 4 statuses should exist in history"
    #     assert 'confirmed' in order_history, "confirmed status should be in history"
    #     assert 'ready_for_pickup' in order_history, "ready_for_pickup status should be in history"
    #     assert 'picked_up' in order_history, "picked_up status should be in history"
    #     assert 'delivered' in order_history, "delivered status should be in history"
    #     assert order_history['picked_up'] <= order_history['delivered'], "confirmed status must come first"


def process_all_events():
    from liborder.domain.order import order_shipment_created, order_ready_for_pickup
    from apporder.workers.order import event_processor
    event_processor(action_code=ActionCode.ORDER_SHIPMENT_CREATED)(order_shipment_created)()
    event_processor(action_code=ActionCode.ORDER_READY_FOR_PICKUP)(order_ready_for_pickup)()
