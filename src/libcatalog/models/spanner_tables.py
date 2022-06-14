from collections import namedtuple
from datetime import date, datetime

from google.cloud import spanner

from libutil.spanner_util import SpannerBaseModel

_Type = namedtuple('_Type', ['type', 'default', 'null'])


def _datetime(dt):
    if isinstance(dt, str):
        try:
            return datetime.strptime(dt, "%Y-%m-%dT%H:%MZ")
        except ValueError as e:
            return datetime.strptime(dt, "%Y-%m-%d")
    elif isinstance(dt, datetime):
        return dt
    elif isinstance(dt, date):
        return datetime.combine(dt, datetime.min.time())
    return None


class Product(SpannerBaseModel):
    _table_name = 'product'
    sku = _Type(str, '', '')
    sku_config = _Type(str, '', '')
    family_code = _Type(str, None, None)
    brand_code = _Type(str, None, None)
    id_product_fulltype = _Type(int, None, None)
    attributes = _Type(str, None, None)
    category_ids = _Type(str, None, None)
    group_code = _Type(str, '', None)
    model_name_number = _Type(str, '', '')
    image_keys = _Type(str, None, None)
    url = _Type(str, None, None)
    catalog_code = _Type(str, None, None)
    is_bulky = _Type(bool, False, False)
    is_active = _Type(bool, True, True)
    created_at = _Type(_datetime, None, None)
    updated_at = _Type(_datetime, spanner.COMMIT_TIMESTAMP, spanner.COMMIT_TIMESTAMP)


class ProductLang(SpannerBaseModel):
    sku = _Type(str, '', '')
    brand = _Type(str, None, None)
    title = _Type(str, None, None)
    title_suffix = _Type(str, None, None)
    meta_keywords = _Type(str, None, None)
    attributes = _Type(str, None, None)
    updated_at = _Type(_datetime, spanner.COMMIT_TIMESTAMP, spanner.COMMIT_TIMESTAMP)


class OfferStock(SpannerBaseModel):
    _table_name = 'offer_stock'
    sku = _Type(str, '', '')
    wh_code = _Type(str, '', '')
    country_code = _Type(str, '', '')
    stock_net = _Type(int, 0, 0)
    updated_at = _Type(_datetime, spanner.COMMIT_TIMESTAMP, spanner.COMMIT_TIMESTAMP)


class Offer(SpannerBaseModel):
    _table_name = 'offer'
    sku = _Type(str, '', '')
    wh_code = _Type(str, '', '')
    country_code = _Type(str, '', '')
    id_partner = _Type(int, None, None)
    msrp = _Type(float, None, None)
    offer_price = _Type(float, None, None)
    stock_customer_limit = _Type(int, None, None)
    updated_at = _Type(_datetime, spanner.COMMIT_TIMESTAMP, spanner.COMMIT_TIMESTAMP)


class ProductMeta(SpannerBaseModel):
    _table_name = 'product_meta'
    sku = _Type(str, '', '')
    volume = _Type(float, None, None)
    weight = _Type(float, None, None)
    updated_at = _Type(_datetime, spanner.COMMIT_TIMESTAMP, spanner.COMMIT_TIMESTAMP)
    updated_by = _Type(str, '', '')
