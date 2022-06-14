import json
import logging
import os
import time

from eventpubsub import EventSubscriber
from eventpubsub import FlowControl
from noonutil.v1 import workerutil

from liborder import Context
from liborder.domain import payment

logger = logging.getLogger(__name__)
MP_CODE = os.getenv('MP_CODE')
workers = workerutil.ThreadedWorkers()
subscriber = EventSubscriber('', workers, flow_control=FlowControl(max_messages=1))


def wrapper_fn(fn, message, subctx):
    data = json.loads(message.data.decode('utf8'))
    logger.info("[%s] got %s", subctx.get('subscription'), data)
    start = time.time()
    fn(data)
    end = time.time()
    logger.info("[%s] done processing %s in %s seconds", subctx.get('subscription'), data, int(end - start))
    message.ack()


def subscribe(*args, **kwargs):
    kwargs['wrapper_fn'] = wrapper_fn
    return subscriber.subscribe(*args, **kwargs)


# TODO: ensure pubsub subscription exists for boilerplate/mp to consume
# this message is published after payment gets authorized and so on
# since boilerplate only to place order (create intent)
# abd authorization is done after intent completed by frontend; this is out of boilerplate scope for now
@subscribe('payment_updated_boilerplate~mp-boilerplate-api')
def boilerplate_payment_update(payload):
    logger.info(f"received an update from mp-payment with payload: {payload}")
    payload = payload['data']
    if payload:
        payload = json.loads(payload)
    if not payload['exref_type']:
        return
    if payload['exref_type'].lower() != 'order' or payload['mp_code'].lower() != MP_CODE.lower():
        return

    order_nr = payload['external_ref']
    with Context.service():
        payment.payment_updated(order_nr)
    logger.info(f"processed payload: {payload}")


if __name__ == "__main__":
    workers.main()
