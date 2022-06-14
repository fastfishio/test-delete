import json
import logging

from appindexing.consumers import subscriber
from libindexing.domain.product import update_zsku_product_details

logger = logging.getLogger(__name__)


def get_json_loads_data(data):
    try:
        return json.loads(data.decode('utf8'))
    except:
        pass
    return data.decode('utf8')


def wrapper_attr_fn(fn, message, subctx):
    data = get_json_loads_data(message.data)
    ids = data if type(data) == list else data.split(',')
    fn(ids)
    message.ack()


@subscriber.subscribe('catalog.zsku_product_updates~mp-boilerplate-api', wrapper_fn=wrapper_attr_fn)
def reindex_zsku_product_details(sku_list):
    update_zsku_product_details(sku_list)
