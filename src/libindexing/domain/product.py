import json
import logging

from boltons import iterutils
from noonhelpers.v1 import auth_team

from libcatalog.domain.category import *
from libcatalog.models.spanner_tables import Product, ProductLang
from libindexing import engine_noon_cache
from libindexing.domain.solr import reindex_product_update_in_solr
from libutil.spanner_util import boilerplate_spanner


logger = logging.getLogger(__name__)


def fetch_zsku_details(sku_list):
    if not sku_list:
        return {}
    dict_res = {}
    for sku_list_chunk in iterutils.chunked(sku_list, 100):
        body = {"skus": sku_list_chunk, "country": "ae", "catalog": "zsku", "marketplace": "noon"}
        headers = {'Content-Type': 'application/json'}
        zsku_api_url = auth_team.get_service_url('ct', 'team-zcatalog-api-marketplace')
        url = f'{zsku_api_url}/sku/retrieve/'
        try:
            ret = auth_team.auth_post(url, timeout=40, payload=body, headers=headers).json()
            dict_res.update(ret)
        except Exception as ex:
            logger.warning(f"error getting zsku details for: {sku_list} - {ex}")
            continue
    return dict_res


def fetch_nsku_details(nsku_list):
    if not nsku_list:
        return {}
    dict_res = {}
    for nsku_list_chunk in iterutils.chunked(nsku_list, 100):

        body = {'ids_product': nsku_list_chunk, 'selectable_columns': []}
        headers = {'Content-Type': 'application/json', 'x-not-csrf': "true", 'Accept': 'application/json'}
        wecat_api_url = auth_team.get_service_url('ct', 'wecat-api')
        # wecat_api_url = "https://wecat-api.ct.noonstg.team"
        url = f'{wecat_api_url}/api/get-products-info/'
        try:
            nsku_details = auth_team.auth_post(url, payload=body, headers=headers, timeout=50).json()
            dict_res.update(nsku_details)
        except Exception as e:
            logger.warning(f"exception getting nsku_details: {e}")
            continue
    return dict_res


def fetch_and_update_product_details(list_products, only_zsku=False, only_nsku=False):
    if not list_products:
        return
    zsku_list = [product['sku'] for product in list_products if product['sku']]
    sku_id_cat_list = get_id_categories_for(zsku_list)
    sku_group_code_map = get_sku_group_code_map_for(zsku_list)
    id_category_to_parent_ids_map = get_id_category_to_parent_ids_map(cached=False)
    product_rows = []
    product_en_rows = []
    product_ar_rows = []
    processed_zskus_list = []
    if not only_nsku:
        ret = fetch_zsku_details(zsku_list)
        for sku, data in ret.items():
            if data.get("error"):
                continue
            product_row = {"sku": sku, "sku_config": sku}
            product_row['family_code'] = data['attributes'].get('family', [{}])[0].get('data')
            product_row['brand_code'] = data['attributes'].get('brand', [{}])[0].get('data')
            model_number = data['attributes'].get('model_number', [{}])[0].get('data', '')
            model_name = data['attributes'].get('model_name', [{}])[0].get('data', '')
            product_row['model_name_number'] = model_name + " " + model_number
            product_row['category_ids'] = ''
            product_row['group_code'] = sku_group_code_map.get(sku, '')
            id_cat_list = [row['id_category'] for row in sku_id_cat_list if row['sku'] == sku]
            if id_cat_list:
                parent_ids = [
                    str(parent_id) for id_cat in id_cat_list for parent_id in id_category_to_parent_ids_map.get(id_cat)
                ]
                parent_ids = list(set(parent_ids))  # get unique elements
                product_row['category_ids'] = ",".join(parent_ids)
            images = data['attributes'].get('image_url', [])
            image_storage_paths = list(map(lambda x: x.get('storage_path'), images))
            image_keys = list(
                map(lambda x: x.replace(".jpg", ""), filter(lambda x: x and x != "", image_storage_paths))
            )
            if image_keys:
                product_row['image_keys'] = json.dumps(image_keys)
            if not product_row.get('image_keys') or product_row.get('image_keys') == '':
                logger.error(f"couldn't extract image_keys from zsku product api of zsku: {sku}")
            product_en_row = {"sku": sku}
            product_ar_row = {"sku": sku}

            for brand in data['attributes']['brand']:
                if brand['locale'] == 'ar':
                    product_ar_row['brand'] = brand['option_name']
                if brand['locale'] == 'en':
                    product_en_row['brand'] = brand['option_name']

            for title in data['attributes']['product_title']:
                if title['locale'] == 'ar':
                    product_ar_row['title'] = title['data']

                if title['locale'] == 'en':
                    product_en_row['title'] = title['data']

            en_attributes = {}
            ar_attributes = {}
            long_desc = data['attributes'].get('long_description')
            if long_desc:
                for entry in long_desc:
                    if entry['locale'] == 'en':
                        en_attributes['long_desc'] = entry['data']
                    elif entry['locale'] == 'ar':
                        ar_attributes['long_desc'] = entry['data']

            product_en_row["attributes"] = json.dumps(en_attributes)
            product_ar_row["attributes"] = json.dumps(ar_attributes)

            title_suffixes = data['attributes'].get('title_suffix', [])
            for suffix in title_suffixes:
                if suffix['locale'] == 'ar':
                    product_ar_row['title_suffix'] = suffix['data']
                if suffix['locale'] == 'en':
                    product_en_row['title_suffix'] = suffix['data']
            processed_zskus_list.append(sku)
            product_rows.append(product_row)
            product_en_rows.append(product_en_row)
            product_ar_rows.append(product_ar_row)

    if not only_zsku:
        nsku_zsku_map = {
            product['nsku']: product['sku']
            for product in list_products
            if product['nsku'] and product['sku'] and product['sku'] not in processed_zskus_list
        }
        nsku_list = list(nsku_zsku_map.keys())
        if nsku_list:
            result = fetch_nsku_details(nsku_list)
            for nsku in result:
                zsku = nsku_zsku_map.get(nsku)
                nsku_details = result[nsku]
                titles = nsku_details.get("attributes", {}).get("product_full_title", [])
                en_title, ar_title = None, None
                for title in titles:
                    if title.get("locale") == "en":
                        en_title = title["value"]
                    elif title.get("locale") == "ar":
                        ar_title = title["value"]

                brand_code, en_brand, ar_brand = None, None, None
                brand_info = nsku_details.get("fundamental_attributes", {}).get("brand", [])
                for brand in brand_info:
                    brand_code = brand.get("code")
                    if brand.get("locale") == "en":
                        en_brand = brand["value"]
                    elif brand.get("locale") == "ar":
                        ar_brand = brand["value"]

                family_code = None
                family_info = nsku_details.get("fundamental_attributes", {}).get("family", [])
                for family in family_info:
                    family_code = family.get("code")
                    break

                id_product_fulltype = None
                fulltype_info = nsku_details.get("fundamental_attributes", {}).get("product_fulltype", [])
                for fulltype in fulltype_info:
                    id_product_fulltype = fulltype.get("id")

                en_title_suffix, ar_title_suffix = None, None
                suffix_info = nsku_details.get("attributes", {}).get("product_full_title", [])
                for suffix in suffix_info:
                    if suffix.get("locale") == "en":
                        en_title_suffix = suffix.get("value")
                    if suffix.get("locale") == "ar":
                        ar_title_suffix = suffix.get("value")

                image_keys = get_image_keys(nsku_details)

                if not (en_title and ar_title and id_product_fulltype and family_code and brand_code):
                    logger.warning(f"some mandatory attributes missing for nsku, zsku: {nsku}:{zsku}")
                    continue
                product_row = {
                    "sku": zsku,
                    "sku_config": zsku,
                    "brand_code": brand_code,
                    "id_product_fulltype": id_product_fulltype,
                    "family_code": family_code,
                }
                product_en_row = {"sku": zsku, "title": en_title, "title_suffix": en_title_suffix, "brand": en_brand}
                product_ar_row = {"sku": zsku, "title": ar_title, "title_suffix": ar_title_suffix, "brand": ar_brand}
                if image_keys:
                    product_row['image_keys'] = json.dumps(image_keys)
                if not product_row.get('image_keys') or product_row.get('image_keys') == '':
                    logger.error(f"couldn't extract image_keys from nsku product api of zsku: {zsku}")
                id_cat_list = [row['id_category'] for row in sku_id_cat_list if row['sku'] == zsku]
                product_row['category_ids'] = ''
                product_row['group_code'] = sku_group_code_map.get(zsku, '')
                if id_cat_list:
                    parent_ids = [
                        str(parent_id)
                        for id_cat in id_cat_list
                        for parent_id in id_category_to_parent_ids_map.get(id_cat)
                    ]
                    parent_ids = list(set(parent_ids))  # get unique elements
                    product_row['category_ids'] = ",".join(parent_ids)
                product_rows.append(product_row)
                product_en_rows.append(product_en_row)
                product_ar_rows.append(product_ar_row)
                processed_zskus_list.append(zsku)
    if product_rows:
        Product.upsert(boilerplate_spanner(), 'product', product_rows)
    if product_en_rows:
        ProductLang.upsert(boilerplate_spanner(), 'product_en', product_en_rows)
    if product_ar_rows:
        ProductLang.upsert(boilerplate_spanner(), 'product_ar', product_ar_rows)
    return processed_zskus_list


def get_image_keys(data):
    keys = []
    for key in data['attributes']:
        if key.startswith("image_url_"):
            image_info = data['attributes'][key]
            for img in image_info:
                if img["meta"]["is_visible"]:
                    meta_data = img['meta']
                    img_url = "v{0}/{1}".format(meta_data['version'], meta_data['public_id'])
                    keys.append({'is_visible': True, 'storage_path': img_url, 'sort_key': meta_data['sort_key']})
    keys = sorted(keys, key=lambda k: k['sort_key'])
    return [key["storage_path"] for key in keys]


def get_product_details_for(sku_list):
    number_of_skus = len(sku_list)
    if number_of_skus == 0:
        return {}
    query = f'''
        SELECT 
            p.sku, p.sku_config, par.title as title_ar, 
            pen.title as title_en, pen.meta_keywords as meta_keywords_en,
            par.meta_keywords as meta_keywords_ar, par.brand as ar_brand,
            pen.brand as en_brand,
            p.category_ids, p.id_product_fulltype, p.image_keys,
            p.brand_code as brand_code,
            p.family_code, p.is_bulky, p.model_name_number,
            p.is_active, p.attributes, p.group_code
        FROM product p 
        JOIN product_en pen USING (sku)
        JOIN product_ar par USING (sku)
        WHERE p.sku in UNNEST(@sku_list)
    '''
    return boilerplate_spanner().execute_query(query, sku_list=sku_list).pk_map()


def update_zsku_product_details(sku_list):
    for i in range(len(sku_list)):
        if sku_list[i][-2:] != "-1":
            sku_list[i] += "-1"
    zsku_nsku_map = sql(
        engine_noon_cache,
        '''
        SELECT zsku_child, nsku_child
        FROM psku.psku
        WHERE zsku_child IN :nsku_list
    ''',
        nsku_list=sku_list,
    ).kv_map()

    products = get_product_details_for(list(zsku_nsku_map.keys()))
    # consider only the product updates for which we already have entry in product table
    active_zsku_nsku_map = {zsku: zsku_nsku_map[zsku] for zsku in list(products.keys())}
    if not active_zsku_nsku_map:
        return

    processed_zskus = fetch_and_update_product_details(
        [{"sku": sku, "nsku": nsku} for sku, nsku in active_zsku_nsku_map.items()]
    )
    if processed_zskus:
        reindex_product_update_in_solr(processed_zskus)
    logger.warning(
        f"active zsku of length {len(active_zsku_nsku_map)} {list(active_zsku_nsku_map.keys())} zsku product update processed of length {len(processed_zskus)} zskus {processed_zskus[0:100]}"
    )


def update_nsku_product_details(nsku_list):
    zsku_nsku_map = sql(
        engine_noon_cache,
        '''
        SELECT zsku_child, nsku_child
        FROM psku.psku
        WHERE 
            nsku_child IN :nsku_list AND
            zsku_child IS NOT NULL''',
        nsku_list=nsku_list,
    ).kv_map()
    products = get_product_details_for(list(zsku_nsku_map.keys()))
    # consider only the product updates for which we already have entry in product table
    active_zsku_nsku_map = {zsku: zsku_nsku_map[zsku] for zsku in list(products.keys())}
    if not active_zsku_nsku_map:
        return
    processed_zsku = fetch_and_update_product_details(
        [{"sku": sku, "nsku": nsku} for sku, nsku in active_zsku_nsku_map.items()]
    )
    if processed_zsku:
        reindex_product_update_in_solr(processed_zsku)
    logger.warning(
        f"nsku update api: active zsku of length {len(active_zsku_nsku_map)} {list(active_zsku_nsku_map.keys())} zsku product update processed of length {len(processed_zsku)} zskus {processed_zsku[0:100]}"
    )
