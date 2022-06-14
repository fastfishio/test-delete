from noonutil.v2 import sqlutil

from libcatalog.models.spanner_tables import OfferStock as SpannerOfferStock
from libindexing import engine_offer
from libindexing.domain.product import *
from libindexing.domain.solr import delete_doc_from_solr, reindex_in_solr
from libindexing.models.noon_cache_spanner_tables import BoilerplateStock
from libindexing.models.tables import OfferStock
from liborder.domain.serviceability import get_wh_code_to_country_code_map
from libutil.spanner_util import noon_cache_spanner
from libutil.spanner_util import sc_spanner


def update_boilerplate_stock(list_products):
    list_to_upsert = []

    zskus = [product['sku'] for product in list_products]
    if zskus:
        existing_zskus = (
            noon_cache_spanner()
            .execute_query('''SELECT sku FROM product WHERE sku IN UNNEST(@list_zsku)''', list_zsku=zskus)
            .scalars()
        )
    else:
        existing_zskus = []

    nskus = [product['nsku'] for product in list_products if product['nsku']]
    if nskus:
        existing_nskus = (
            noon_cache_spanner()
            .execute_query(
                '''
            SELECT sku
            FROM product
            WHERE sku IN UNNEST(@list_nsku)
        ''',
                list_nsku=nskus,
            )
            .scalars()
        )
    else:
        existing_nskus = []

    list_zsku_products = [product for product in list_products if product['sku'] in existing_zskus]

    param_list_sku = [(product['nsku'], product['wh_code']) for product in list_zsku_products if product['nsku']]
    if param_list_sku:
        noon_cache_spanner().execute_update(
            '''
            DELETE FROM
                boilerplate_stock
            WHERE(sku, wh_code) in UNNEST(@sku_wh_code)
        ''',
            sku_wh_code=param_list_sku,
        )

    list_to_upsert.extend(
        [
            {
                'sku': product['sku'],
                'boilerplate_sku': product['sku'],
                'stock_net': product['stock_net'],
                'country_code': product['country_code'],
                'wh_code': product['wh_code'],
            }
            for product in list_zsku_products
        ]
    )

    list_nsku_products = [
        product
        for product in list_products
        if product['sku'] not in existing_zskus and product['nsku'] in existing_nskus
    ]

    list_to_upsert.extend(
        [
            {
                'sku': product['nsku'],
                'boilerplate_sku': product['sku'],
                'stock_net': product['stock_net'],
                'country_code': product['country_code'],
                'wh_code': product['wh_code'],
            }
            for product in list_nsku_products
        ]
    )
    if list_to_upsert:
        BoilerplateStock.upsert(noon_cache_spanner(), 'boilerplate_stock', list_to_upsert)


def stock_update(scstock_rows, force_product_update=False):
    if not scstock_rows:
        return
    psku_code_map = sql(
        engine_noon_cache,
        '''
        SELECT psku_code, zsku_child as sku, nsku_child as nsku, id_partner
        FROM psku.psku
        WHERE psku_code IN :psku_code_list
        AND zsku_child IS NOT NULL
    ''',
        psku_code_list=[row['psku_code'] for row in scstock_rows],
    ).pk_map()

    stock_update_rows = [
        {
            'wh_code': row['wh_code'],
            'stock_net': (row['qty_net'] if row['qty_net'] >= 0 else 0),
            'sku': psku_code_map[row['psku_code']]['sku'],
            'nsku': psku_code_map[row['psku_code']]['nsku'],
            'id_partner': psku_code_map[row['psku_code']]['id_partner'],
            'country_code': row['country_code'],
        }
        for row in scstock_rows
        if row['psku_code'] in psku_code_map
    ]
    if not scstock_rows:
        return

    if force_product_update:
        sku_to_product_map = []
    else:
        sku_to_product_map = get_product_details_for([row['sku'] for row in stock_update_rows])

    skus_with_no_product_data = [
        {'sku': row['sku'], 'nsku': row['nsku']} for row in stock_update_rows if row['sku'] not in sku_to_product_map
    ]
    processed_zskus_list = []
    if skus_with_no_product_data:
        processed_zskus_list = fetch_and_update_product_details(skus_with_no_product_data)

    stock_update_rows = [
        row for row in stock_update_rows if row['sku'] in processed_zskus_list or row['sku'] in sku_to_product_map
    ]

    sqlutil.upsert_batch(engine_offer, OfferStock, stock_update_rows)
    SpannerOfferStock.upsert(boilerplate_spanner(), 'offer_stock', stock_update_rows)
    update_boilerplate_stock(stock_update_rows)

    country_codes = ('ae', 'sa', 'eg')
    for country_code in country_codes:
        skus_to_delete_from_solr = [
            f"{row['sku']}:{row['wh_code']}"
            for row in stock_update_rows
            if row['stock_net'] == 0 and row['country_code'].lower() == country_code
        ]
        if skus_to_delete_from_solr:
            delete_doc_from_solr(skus_to_delete_from_solr, country_code)

    skus_to_add_to_solr = [(row['sku'], row['wh_code']) for row in stock_update_rows]
    reindex_in_solr(skus_to_add_to_solr)


def reindex_stock(psku_code_wh_code_list):
    wh_code_cc_map = get_wh_code_to_country_code_map()
    wh_codes_not_serviceable = {
        row['warehouse_code'] for row in psku_code_wh_code_list if row['warehouse_code'] not in wh_code_cc_map.keys()
    }
    psku_code_wh_code_list = [row for row in psku_code_wh_code_list if row['warehouse_code'] in wh_code_cc_map.keys()]
    if wh_codes_not_serviceable:
        logger.warning(f"following warehouses are not part of boilerplate {wh_codes_not_serviceable}")
    if not psku_code_wh_code_list:
        return
    stock_rows = (
        sc_spanner()
        .execute_query(
            '''
        SELECT psku_code, warehouse_code as wh_code, qty_net
        FROM stock
        WHERE 
        (psku_code, warehouse_code) in UNNEST(@psku_code_wh_code_list)
    ''',
            psku_code_wh_code_list=[(row['psku_code'], row['warehouse_code']) for row in psku_code_wh_code_list],
        )
        .dicts()
    )
    if not stock_rows:
        return
    for row in stock_rows:
        row['country_code'] = wh_code_cc_map[row['wh_code']].upper()
    stock_update(stock_rows)


def full_stock_update_for_warehouse(wh_code):
    wh_code_cc_map = get_wh_code_to_country_code_map()
    if wh_code not in wh_code_cc_map.keys():
        logger.warning(f"skipping full stock stock update for {wh_code} as it is not on boilerplate")
        return
    country_code = wh_code_cc_map[wh_code].upper()
    stock_rows = (
        sc_spanner()
        .execute_query(
            '''
        SELECT psku_code, warehouse_code as wh_code, qty_net, @country_code as country_code
        FROM stock
        WHERE 
        warehouse_code = @wh_code
    ''',
            wh_code=wh_code,
            country_code=country_code,
        )
        .dicts()
    )
    if not stock_rows:
        return
    stock_update(stock_rows, force_product_update=True)
