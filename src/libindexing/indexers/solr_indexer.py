from libindexing.domain.solr import SolrIndexer
from libindexing.domain.solr import get_attrs
from libutil.spanner_util import *

"""
This is a test file to load sample data in solr
"""
solr_indexers = {
    "ae": SolrIndexer(os.getenv('SOLR_HOST', 'solr'), "offer_ae")
}


def load_sample_products_in_solr(country_code):
    spanner_query = '''
        SELECT p.sku, o.wh_code, o.offer_price, 
        par.title as title_ar, pen.title as title_en,
        pen.meta_keywords as meta_keywords_en,
        par.meta_keywords as meta_keywords_ar,
        par.brand as ar_brand,
        pen.brand as en_brand,
        p.category_ids,
        p.brand_code as brand_code,
        os.stock_net,
        p.family_code, p.brand_code,
        p.is_active, p.attributes
        FROM offer o
        JOIN offer_stock os ON o.sku = os.sku 
        AND o.wh_code = os.wh_code
        JOIN product p on p.sku = o.sku
        JOIN product_ar par on p.sku = par.sku 
        JOIN product_en pen on p.sku = pen.sku
        LIMIT 500
    '''
    rows = boilerplate_spanner().execute_query(spanner_query).dicts()
    print([r['title_en'] for r in rows])
    solr_rows = []
    solr_rows_to_delete = []
    for r in rows:
        solr_row = {}
        solr_row['object_id'] = f"{r['sku']}:{r['wh_code']}"
        if r["stock_net"] <= 0:
            solr_rows_to_delete.append(solr_row['object_id'])
        solr_row["sku"] = r["sku"]
        solr_row["en_title"] = r["title_en"]
        solr_row["ar_title"] = r["title_ar"] or r["title_en"]
        solr_row["brand_code"] = r['brand_code']
        solr_row["en_brand"] = r['en_brand']
        solr_row["ar_brand"] = r['ar_brand']
        solr_row["wh_code"] = r['wh_code']
        if r["offer_price"]:
            solr_row["price"] = float(r['offer_price'])
        if r["category_ids"]:
            solr_row["cat"] = list(map(int, r["category_ids"].split(",")))
        if r["attributes"]:
            solr_row.update(
                {'attr_{}'.format(key): value for key, value in get_attrs(r["attributes"]).items() if value})
        solr_rows.append(solr_row)
    solr_indexers.get(country_code).add_objects(solr_rows)

# if __name__ == "__main__":
#     load_sample_products_in_solr("ae")
