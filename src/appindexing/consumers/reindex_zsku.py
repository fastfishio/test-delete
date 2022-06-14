from appindexing.consumers import subscriber
from libindexing.domain.product import update_zsku_product_details


@subscriber.subscribe('boilerplate_reindex_sku~mp-boilerplate-api')
def reindex_sku_details(zsku_list):
    update_zsku_product_details(zsku_list)
