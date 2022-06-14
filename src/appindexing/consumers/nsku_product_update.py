import logging

from appindexing.consumers import subscriber
from libindexing.domain.product import update_nsku_product_details

logger = logging.getLogger(__name__)


def wrapper_fn(fn, message, subctx):
    ids = message.data.decode('utf8').split(',')
    fn(ids)
    message.ack()


#TODO: Rename the subscriber after creating on pubsub
@subscriber.subscribe('update_log.product_update~mp-boilerplate-api', wrapper_fn=wrapper_fn)
def reindex_nsku_product_details(nsku_list):
    update_nsku_product_details(nsku_list)
