import logging
import time

from jsql import sql
from noonutil.v1 import workerutil

from apporder.workers import event_processor
from liborder import engine
from liborder.context import Context
from liborder.domain import boilerplate_event
from liborder.domain import payment, order, credit
from liborder.domain.enums import Status, PaymentMethod, PREPAID_PAYMENT_METHOD_CODES
from liborder.domain.status import PaymentStatus, ORDER_TERMINAL_STATES

logger = logging.getLogger(__name__)

workers = workerutil.ThreadedWorkers()


@workers.register
@event_processor(action_code=boilerplate_event.ActionCode.PAYMENT_ORDER_CREATE, sleep_time=0)
def worker_payment_order_create(event):
    payment.payment_order_create(event)


# todo: see if these workers can be moved to lib so that they can be independently tested
@workers.register
@event_processor(action_code=boilerplate_event.ActionCode.PAYMENT_ORDER_CAPTURE, sleep_time=2)
def worker_payment_order_capture(event):
    payment.capture_payment_amount(event)


# this won't be very effective once the order table grows
#  rethink about the way to do it effectively
#  direct settlement is used in case of payment failed, and amount is deducted from credit first
#  so we credit the amount back to the credit from this flow
#  same flow would be triggered
@workers.register
def worker_payment_direct_settlement():
    valid_method_codes = PREPAID_PAYMENT_METHOD_CODES + [PaymentMethod.NOPAYMENT.value]
    order_nr_list = sql(engine, '''
        SELECT order_nr
        FROM sales_order
        WHERE (payment_method_code IN :valid_method_codes_list OR status_code_order IN :order_final_states_list)
        AND order_collect_from_customer < order_collected_from_customer
        AND created_at > UTC_TIMESTAMP() - INTERVAL :hour HOUR
    ''', valid_method_codes_list=valid_method_codes, order_final_states_list=list(ORDER_TERMINAL_STATES),
                        hour=10).scalars()
    for order_nr in order_nr_list:
        with Context.service():
            payment.settle_payment(order_nr)


# this won't be very effective once the order table grows
#  rethink about the way to do it effectively, perhaps we should have a created_at filter?
#  this flow would be triggered when order is canceled
#  and we have some amount authorized/captured
#  we should reverse the transaction
@workers.register
def worker_cancel_authorized():
    with Context.service():
        order.order_cancel_authorized()
    time.sleep(20)


@workers.register
def mark_payment_timeout_failed():
    order_nr_list = sql(engine, '''
        SELECT order_nr
        FROM sales_order
        WHERE created_at < UTC_TIMESTAMP() - INTERVAL :timeout MINUTE
        AND status_code_payment = :pending
    ''', pending=Status.PENDING.value, timeout=5).scalars()
    for order_nr in order_nr_list:
        with Context.service():
            logger.info(f"marking the payment as failed from worker: {order_nr}")
            PaymentStatus(order_nr, ctx={'reason': 'payment pending timeout'}).transition(Status.FAILED.value)
    time.sleep(10)


# ideally, this worker should not exist
#  we have SETTLE_PAYMENT events at all apporopriate points so that settle_payment should get triggered
#  ready_for_pickup, delivered, undelivered, canceled, adjustment, failed etc
#  but still keeping it here to avoid any missing case - and it would be triggered only after 5 hours of order placed
#  since there are other triggers that should take care of this
# as the sales_order table grows, this query would become expensive, so find a better way
@workers.register
def worker_payment_settlement():
    order_nr_list = sql(engine, '''
        SELECT order_nr
        FROM sales_order
        WHERE created_at < UTC_TIMESTAMP() - INTERVAL :timeout HOUR
        AND UTC_TIMESTAMP() > created_at + INTERVAL 5 HOUR
        AND order_collect_from_customer != order_collected_from_customer
        AND status_code_order IN :order_final_states_list
    ''', timeout=24, order_final_states_list=list(ORDER_TERMINAL_STATES)).scalars()
    for order_nr in order_nr_list:
        with Context.service():
            logger.info(f"settling payment via worker for: {order_nr}")
            payment.settle_payment(order_nr)
    time.sleep(10)


@workers.register
@event_processor(action_code=boilerplate_event.ActionCode.CAPTURE_ISSUED_CREDITS)
def worker_capture_issued_credits(event):
    credit.capture_issued_credits(event)


@workers.register
@event_processor(action_code=boilerplate_event.ActionCode.SETTLE_PAYMENT, sleep_time=10)
def worker_settle_payment(event):
    order_nr = event['data']['order_nr']
    payment.settle_payment(order_nr=order_nr)


if __name__ == "__main__":
    workers.main()
