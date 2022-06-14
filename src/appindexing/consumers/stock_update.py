from appindexing.consumers import subscriber
from libindexing.domain.product import *
from libindexing.domain.stock import reindex_stock


@subscriber.subscribe('scstock_darkstore_stock_net_updated~mp-boilerplate-api')
def reindex_stock_update(payload):
    logger.info(f"stock_updated payload: {payload['data']}")
    list_stock_update = json.loads(payload['data'])['updated_stock']
    reindex_stock(list_stock_update)
