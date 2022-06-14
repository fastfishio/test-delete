import logging

from . import consume_workers
from . import price_update
from . import stock_update
from . import nsku_product_update
from . import zsku_product_update
from . import reindex_zsku

assert price_update
assert stock_update
assert nsku_product_update
assert zsku_product_update
assert reindex_zsku
logger = logging.getLogger(__name__)

consume_workers.main()
