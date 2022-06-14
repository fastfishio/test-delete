from noonutil.v1 import sqlenrich, miscutil

from libindexing import engine_noon_patalog, engine_order


@miscutil.threadsafe_singleton
def get_enricher():
    enricher = sqlenrich.Enricher()
    enricher.add_sql_dataset(
        'ds_psku',
        'id_partner psku_canonical',
        engine_noon_patalog,
        '''SELECT p.id_partner, p.psku_canonical, catalog_sku
        FROM psku p
        LEFT JOIN psku_catalog_map pm USING(psku_code)
        WHERE p.is_active=1 AND pm.id_catalog = 9
        AND (p.id_partner, psku_canonical) IN :x_tuple_list''',
    )
    enricher.add_sql_dataset(
        'ds_warehouse',
        'wh_code country_code',
        engine_order,
        '''SELECT wh_code, country_code
        FROM warehouse
        WHERE (wh_code, country_code) IN :x_tuple_list''',
    )
    return enricher
