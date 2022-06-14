from typing import Any, Dict, List, Set

from jsql import sql
from noonutil.v1 import miscutil

from liborder import ctx
from libutil import util
import logging


class DeliveryPreference(util.NoonBaseModel):
    code: str
    name: str
    value: bool = False


@miscutil.cached(ttl=60 * 60 * 60)
def __get_cached_delivery_preferences() -> List[Dict[str, Any]]:
    return sql(
        ctx.conn,
        '''
        SELECT id_delivery_preference, code, name_en, name_ar, allowed_for_cod
        FROM delivery_preference
        WHERE is_active = 1
    ''',
    ).dicts()


def __get_delivery_preferences(postpaid: bool, enabled_delivery_preferences_ids: Set[int]) -> List[DeliveryPreference]:
    preferences = __get_cached_delivery_preferences()
    if postpaid:
        preferences = [pref for pref in preferences if pref['allowed_for_cod']]
    for preference in preferences:
        # TODO: @abdallah, Is this safe for multithreading ? or no multithreading in the boilerplate ?
        preference['name'] = preference[f'name_{ctx.lang}']
        preference['value'] = preference['id_delivery_preference'] in enabled_delivery_preferences_ids
    return [DeliveryPreference(**preference) for preference in preferences]


def get_order_delivery_preferences(order_nr: str, postpaid: bool) -> List[DeliveryPreference]:
    delivery_preferences_ids = sql(
        ctx.conn,
        """SELECT dp.id_delivery_preference FROM sales_order_delivery_preference dp
    INNER JOIN sales_order so USING(id_sales_order)
    WHERE so.order_nr = :order_nr""",
        order_nr=order_nr,
    ).scalar_set()
    return __get_delivery_preferences(postpaid, delivery_preferences_ids)


def get_session_delivery_preferences(session_code: str, postpaid: bool) -> List[DeliveryPreference]:
    delivery_preferences_ids = sql(
        ctx.conn,
        """SELECT dp.id_delivery_preference FROM session_delivery_preference dp
    INNER JOIN session s USING(id_session)
    WHERE s.session_code = :session_code""",
        session_code=session_code,
    ).scalar_set()
    return __get_delivery_preferences(postpaid, delivery_preferences_ids)
