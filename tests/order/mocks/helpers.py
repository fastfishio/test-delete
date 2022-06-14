import json
import os

from noonutil.v1 import spannerutil
from noonutil.v1 import storageutil

from liborder.context import ctx

SPANNER_PROJECT_NAME = os.getenv('BOILERPLATE_SPANNER_PROJECT')
SPANNER_INSTANCE_ID = os.getenv('BOILERPLATE_SPANNER_INSTANCE_ID')
SPANNER_DATABASE_ID = os.getenv('BOILERPLATE_SPANNER_DATABASE_ID')


def get_spanner_db():
    return spannerutil.SpannerDB(project=SPANNER_PROJECT_NAME, instance=SPANNER_INSTANCE_ID, db=SPANNER_DATABASE_ID)


def patched_enrich_offers(keys):
    if not keys:
        return {}
    assert ctx.lang in ['ar', 'en'], "Invalid language"
    enriched_offers = get_spanner_db().execute_query(f'''
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
    ''', keys=keys, key_order={'keys': ('sku', 'wh_code')}).dicts()
    for offer in enriched_offers:
        offer['title'] = offer[f'title_{ctx.lang}']
        offer['brand'] = offer[f'brand_{ctx.lang}']
        # Should we have a constant limit here?
        offer['qty_max'] = min(offer['stock_net'], offer['stock_customer_limit'], 20)
        if offer['image_keys']:
            image_keys = json.loads(offer['image_keys'])
            offer['image_key'] = image_keys[0] if image_keys else None
    ret = {
        (offer['sku'], offer['wh_code']): offer
        for offer in enriched_offers
    }
    for key in keys:
        ret[key]['price'] = 100
    return ret


def mock_read_from_cloud(file_name, bucket):
    if 'ae' in file_name:
        kml_file_path = '/src/tests/order/data/test_ae.kml'
    else:
        raise NotImplementedError(f"kml file should contain either 'ae' or 'sa' in name ")
    with open(kml_file_path) as f:
        return bytes(f.read(), 'utf-8')


storageutil.read_from_gcloud = mock_read_from_cloud
