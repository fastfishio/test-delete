import logging

from noonutil.v1 import workerutil

from apporder.workers import event_processor
from liborder.domain import boilerplate_event, notification
from liborder.domain import order

logger = logging.getLogger(__name__)

workers = workerutil.ThreadedWorkers()


@workers.register
@event_processor(action_code=boilerplate_event.ActionCode.ORDER_SHIPMENT_CREATED)
def process_order_shipment_created(event):
    order.order_shipment_created(event)


@workers.register
@event_processor(action_code=boilerplate_event.ActionCode.ORDER_READY_FOR_PICKUP)
def process_order_ready_for_pickup(event):
    order.order_ready_for_pickup(event)


@workers.register
@event_processor(action_code=boilerplate_event.ActionCode.CANCEL_ORDER_WITH_NO_SHIPMENTS)
def cancel_order_with_no_shipments(event):
    order.cancel_order_with_no_shipments(event)


@workers.register
@event_processor(action_code=boilerplate_event.ActionCode.NOTIFICATION_ORDER_UPDATE)
def worker_notification_order_update(event):
    notification.notification_order_update(event)


@workers.register
@event_processor(action_code=boilerplate_event.ActionCode.DEFAULT_PAYMENT_UPDATE, sleep_time=30)
def update_default_payment_method(event):
    order.update_default_payment_method(event)


if __name__ == "__main__":
    workers.main()
