from appindexing.consumers import subscriber
from libindexing.domain.price import reindex_price
from libindexing.domain.product import *


def wrapper_fn(fn, message, subctx):
    ids = message.data.decode('utf8')
    fn(ids)
    message.ack()


def subscribe(*args, **kwargs):
    kwargs['wrapper_fn'] = wrapper_fn
    return subscriber.subscribe(*args, **kwargs)


@subscribe('boilerplate_price_update~mp-boilerplate-api')
def reindex_price_update(payload):
    json_payload = json.loads(payload)
    sku_wh_code_list = [(offer['sku'], offer['wh_code']) for offer in json_payload]
    reindex_price(sku_wh_code_list)
