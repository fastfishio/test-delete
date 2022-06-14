from jsql import sql

from libcatalog.models.spanner_tables import Offer
from libindexing import engine_offer, engine_noon_cache
from libindexing.domain.product import get_product_details_for, fetch_and_update_product_details
from libindexing.domain.solr import reindex_in_solr
from libutil.spanner_util import boilerplate_spanner


def reindex_price(sku_wh_code_list):
    offers = sql(
        engine_offer,
        '''
                SELECT * FROM offer
                WHERE (sku, wh_code) IN :sku_wh_code_tuple_list
            ''',
        sku_wh_code_tuple_list=sku_wh_code_list,
    ).dicts()
    rows = [
        {
            "sku": offer_row['sku'],
            "offer_price": offer_row["offer_price"],
            "msrp": offer_row["msrp"],
            "wh_code": offer_row["wh_code"],
            "id_partner": offer_row["id_partner"],
            "country_code": offer_row["country_code"],
            "stock_customer_limit": 10,
        }
        for offer_row in offers
    ]

    # should we check for existence of product data only for stock update and not for price update?
    skus = [row['sku'] for row in rows]

    product_details = get_product_details_for(skus)

    missing_skus = [sku for sku in skus if sku not in product_details]

    missing_sku_nsku_list = sql(
        engine_noon_cache,
        '''
        SELECT zsku_child as sku, nsku_child as nsku
        FROM psku.psku
        WHERE zsku_child IN :sku_list
    ''',
        sku_list=missing_skus,
    ).dicts()

    processed_zskus = []
    if missing_sku_nsku_list:
        processed_zskus = fetch_and_update_product_details(missing_sku_nsku_list)

    valid_rows = [row for row in rows if row['sku'] in processed_zskus or row['sku'] in product_details]

    if valid_rows:
        Offer.upsert(boilerplate_spanner(), 'offer', valid_rows)
        reindex_in_solr([(offer['sku'], offer['wh_code']) for offer in valid_rows])
