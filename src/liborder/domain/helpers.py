import json
import logging
import os

from jsql import sql
from noonutil.v1 import spannerutil, miscutil

from liborder import engine
from liborder.context import ctx

logger = logging.getLogger(__name__)

BOILERPLATE_SPANNER_INSTANCE_ID = os.getenv('BOILERPLATE_SPANNER_INSTANCE_ID')
BOILERPLATE_SPANNER_DATABASE_ID = os.getenv('BOILERPLATE_SPANNER_DATABASE_ID')
BOILERPLATE_SPANNER_PROJECT = os.getenv('BOILERPLATE_SPANNER_PROJECT')


def get_spanner_db():
    return spannerutil.SpannerDB(
        project=BOILERPLATE_SPANNER_PROJECT,
        instance=BOILERPLATE_SPANNER_INSTANCE_ID,
        db=BOILERPLATE_SPANNER_DATABASE_ID,
    )


def enrich_offers(keys):
    if not keys:
        return {}
    assert ctx.lang in ['ar', 'en'], "Invalid language"
    enriched_offers = (
        get_spanner_db()
        .execute_query(
            f'''
        SELECT
            offer.sku,
            id_partner,
            wh_code,
            offer_price as price,
            msrp,
            stock_net,
            stock_customer_limit,
            image_keys,
            id_product_fulltype,
            p_ar.title as title_ar,
            p_ar.title_suffix as title_suffix_ar,
            p_ar.brand as brand_ar,
            p_en.title as title_en,
            p_en.title_suffix as title_suffix_en,
            p_en.brand as brand_en,
        FROM offer
        LEFT JOIN offer_stock USING(sku, wh_code)
        LEFT JOIN product USING(sku)
        LEFT JOIN product_ar p_ar USING(sku)
        LEFT JOIN product_en p_en USING(sku)
        LEFT JOIN product_meta USING(sku)
        WHERE STRUCT< sku STRING, wh_code STRING> (sku, wh_code) in UNNEST(@keys)
    ''',
            keys=keys,
            key_order={'keys': ('sku', 'wh_code')},
        )
        .dicts()
    )
    for offer in enriched_offers:
        offer['title'] = offer[f'title_{ctx.lang}']
        offer['brand'] = offer[f'brand_{ctx.lang}']
        # Should we have a constant limit here?
        offer['qty_max'] = min(offer['stock_net'] or 0, offer['stock_customer_limit'] or 20, 20)
        if offer['image_keys']:
            image_keys = json.loads(offer['image_keys'])
            offer['image_key'] = image_keys[0] if image_keys else None
        else:
            offer['image_key'] = None
    return {(offer['sku'], offer['wh_code']): offer for offer in enriched_offers}


@miscutil.cached(ttl=60 * 60 * 2)
def get_cancel_reason_map(internal, item_level):
    cancel_reasons = get_cancel_reasons(internal, item_level)
    return {reason['code']: {'name_en': reason['name_en'], 'name_ar': reason['name_ar']} for reason in cancel_reasons}


@miscutil.cached(ttl=60 * 60 * 2)
def get_cancel_reasons(internal, item_level):
    order_level = 1 - item_level
    return sql(
        ctx.conn,
        '''
        SELECT code, name_en, name_ar
        FROM cancel_reason
        WHERE is_internal = :internal
        {% if item_level %}
            AND is_item_level = 1
        {% endif %}
        {% if order_level %}
            AND is_order_level = 1
        {% endif %}
        AND is_active = 1
    ''',
        item_level=item_level,
        order_level=order_level,
        internal=internal,
    ).dicts()


@miscutil.cached(ttl=60)
def get_status_map():
    return sql(
        ctx.conn,
        '''
        SELECT code, name_en, name_ar
        FROM status
    ''',
    ).pk_map()


@miscutil.cached(ttl=60 * 60 * 60)
def get_country_details_map():
    return sql(ctx.conn, '''SELECT country_code, currency_code, time_zone FROM country''').pk_map()


@miscutil.cached(ttl=60 * 60 * 60)
def get_warehouses_for_country(country_code):
    # not using ctx.conn here since it is called in before_request of catalog APIs which doesn't have ctx
    warehouses = sql(
        engine,
        '''SELECT wh_code, area_name_en, area_name_ar, city_en, city_ar, lat, lng, delivery_fee, min_order
        FROM warehouse
        WHERE country_code=:country_code AND is_active = 1''',
        country_code=country_code,
    ).dicts()
    return warehouses


@miscutil.cached(ttl=60 * 60 * 60)
def get_all_warehouses():
    warehouses = sql(
        engine,
        '''SELECT wh_code, area_name_en, area_name_ar, city_en, city_ar, lat, lng, delivery_fee, min_order
        FROM warehouse
        WHERE is_active = 1''',
    ).dicts()
    return warehouses


def get_warehouse_details(country_code, wh_code):
    warehouses = get_warehouses_for_country(country_code)
    for warehouse in warehouses:
        if warehouse['wh_code'] == wh_code:
            return warehouse
