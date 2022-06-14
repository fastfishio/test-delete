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


class BoilerplateStock(SpannerBaseModel):
    _table_name = 'boilerplate_stock'
    sku = _Type(str, '', '')
    boilerplate_sku = _Type(str, '', '')
    wh_code = _Type(str, '', '')
    country_code = _Type(str, '', '')
    stock_net = _Type(int, 0, 0)
    updated_at = _Type(_datetime, spanner.COMMIT_TIMESTAMP, spanner.COMMIT_TIMESTAMP)
