import json
import threading

import pysolr
from noonutil.v1 import miscutil
from noonutil.v2.sqlutil import chunker

from libindexing.domain.offer import get_product_and_offer_details_for, get_in_stock_offers
from libutil.spanner_util import *

SOLR_SEMAPHORE = os.getenv('SOLR_SEMAPHORE') or 2

logger = logging.getLogger(__name__)

SOLR_HOST = os.getenv('SOLR_HOST') or 'localhost'


class SolrIndexer(object):
    DOC_SIZE = 250
    UPDATE_KWARGS = {'commit': True, 'softCommit': True}

    def __init__(self, host, index="", timeout=10):
        kwargs = {"timeout": timeout}
        self.solr = pysolr.Solr(f'http://{host}:8983/solr/{index}/', **kwargs)
        self.lock = threading.Semaphore(SOLR_SEMAPHORE)

    def add_objects(self, data):
        for chunk_data in chunker(self.DOC_SIZE, data):
            self.add_chunk(chunk_data)

    @retry(stop_max_attempt_number=3, wait_random_min=1000, wait_random_max=5000)
    def add_chunk(self, documents):
        with self.lock:
            self.solr.add(documents, **self.UPDATE_KWARGS)

    @retry(stop_max_attempt_number=3, wait_random_min=1000, wait_random_max=5000)
    def delete_chunk(self, chunk_data):
        with self.lock:
            self.solr.delete(id=chunk_data, **self.UPDATE_KWARGS)

    def delete_objects(self, data):
        for chunk_data in chunker(self.DOC_SIZE, data):
            self.delete_chunk(chunk_data)


solr_indexers = {
    "ae": SolrIndexer(os.getenv('SOLR_HOST', 'solr'), "offer_ae")
}


def reindex_product_update_in_solr(sku_list):
    if not sku_list:
        return
    offers = get_in_stock_offers(sku_list)
    solr_docs = {
        "ae": []
    }

    for row in offers:
        country_code = row.get("country_code").lower()
        solr_docs[country_code].append(get_solr_doc(row))

    for key in solr_docs:
        solr_indexers[key].add_objects(solr_docs[key])


# todo: test this
def reindex_in_solr(sku_wh_code_list):
    offers = get_product_and_offer_details_for(sku_wh_code_list)
    in_stock_spanner_rows = [row for row in offers if row['stock_net'] > 0]
    solr_docs = {}
    for country_code, offers in miscutil.groupby(in_stock_spanner_rows, lambda x: x["country_code"].lower()):
        country_code = country_code.lower()
        solr_docs[country_code] = []
        for row in offers:
            solr_docs[country_code].append(get_solr_doc(row))
    for key in solr_docs:
        solr_indexers[key].add_objects(solr_docs[key])


def get_solr_doc(row):
    solr_row = {}
    solr_row['object_id'] = f"{row['sku']}:{row['wh_code']}"
    solr_row["sku"] = row["sku"]
    solr_row["en_title"] = row["title_en"]
    solr_row["ar_title"] = row["title_ar"] or row["title_en"]
    solr_row["wh_code"] = row['wh_code']
    solr_row["brand_code"] = row['brand_code']
    solr_row["en_brand"] = row['en_brand']
    solr_row["ar_brand"] = row['ar_brand']
    if row["offer_price"]:
        solr_row["price"] = float(row['offer_price'])
    if row["category_ids"]:
        solr_row["cat"] = list(map(int, row["category_ids"].split(",")))
    solr_row["group_code"] = row["group_code"]
    if row["attributes"]:
        solr_row.update(
            {'attr_{}'.format(key): value for key, value in get_attrs(row["attributes"]).items() if value})
    return solr_row


def get_attrs(attributes):
    attributes = json.loads(attributes)

    def get_attributes_code(attrs_json):
        attr_code = {'code': {}}
        if attrs_json:
            if 'code' in attrs_json:
                attr_code['code'].update(attrs_json['code'])
        return attr_code['code']

    def get_attributes_lang(attributes_dict, lang):
        attr_lang = {lang: {}}
        if attributes_dict:
            if lang in attributes_dict:
                attr_lang[lang].update(attributes_dict[lang])
        return attr_lang[lang]

    attrs = get_attributes_code(attributes)
    attrs.update(get_attributes_lang(attributes, "ar"))
    attrs.update(get_attributes_lang(attributes, "en"))
    return attrs


def delete_doc_from_solr(object_id, country_code):
    solr_indexers[country_code].delete_objects(object_id)

# if __name__ == "__main__":
#     reindex_product_update_in_solr(['Z008431D8F223B31EF128Z-1', 'Z012D6B3B4956DEF77B48Z-1', 'Z0174C34FC6F5FBDACC61Z-1', 'Z019FDA9EAE0889BA47A9Z-1'])
#
