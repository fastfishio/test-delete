import json
import logging

from boltons import iterutils
from jsql import sql
from noonutil.v2 import sqlutil

from libcatalog import engine, engine_noon_mp_cache_ro
from libcatalog.models import tables
from libcatalog.models.spanner_tables import ProductMeta
from libindexing.domain.product import get_product_details_for, fetch_and_update_product_details
from libutil import pubsub
from libutil.spanner_util import boilerplate_spanner
from noonutil.v1 import miscutil

IMPORTERS = {}
logger = logging.getLogger(__name__)


def register(fn):
    IMPORTERS[fn.__name__.replace('import_', '')] = fn
    return fn


def import_rows(key, rows, email, *, chunk_size=500):
    importer = IMPORTERS.get(key)
    if importer is None:
        raise ValueError(f'unknown importer {key}')
    importer(rows, email)


@register
def import_product_meta(rows, email=''):
    for r in rows:
        if r['volume']:
            assert 0 <= float(r['volume']) <= 25000, 'volume must be between 1 and 25000'
            r['volume'] = float(r['volume'])
        else:
            r['volume'] = None
        if r['weight']:
            assert 0 <= float(r['weight']) <= 7, 'weight must be below 7 kgs'
            r['weight'] = float(r['weight'])
        else:
            r['weight'] = None
        r['updated_by'] = email

    list_zsku = [r['sku'] for r in rows]

    existing_zskus = get_product_details_for(list_zsku)

    list_missing_zsku = [zsku for zsku in list_zsku if zsku not in existing_zskus]
    list_sku_nsku = []
    if list_missing_zsku:
        list_sku_nsku = sql(
            engine_noon_mp_cache_ro,
            '''
            SELECT nsku_child as nsku, zsku_child as sku
            FROM psku.psku
            WHERE zsku_child IN :zsku_list
        ''',
            zsku_list=list_missing_zsku,
        ).dicts()

    processed_zskus_list = []
    if list_sku_nsku:
        processed_zskus_list = fetch_and_update_product_details(list_sku_nsku)
    rows = [r for r in rows if r['sku'] in processed_zskus_list or r['sku'] in existing_zskus]

    sqlutil.upsert_batch(engine, tables.ProductMeta, rows)
    ProductMeta.upsert(boilerplate_spanner(), 'product_meta', rows)


@register
def import_product_group_code(rows, email=''):
    for r in rows:
        r['updated_by'] = email
    sqlutil.upsert(
        engine, tables.ProductGroupCode, rows, unique_columns=['sku'], update_columns=['group_code', 'updated_by']
    )

    publisher = pubsub.get_publisher('boilerplate_reindex_sku')
    zskus = miscutil.pluck('sku', rows)
    for chunk in iterutils.chunked(zskus, 200):
        publisher(json.dumps(chunk))
    logger.info(f"published {zskus} to boilerplate_reindex_sku after group code update")


@register
def import_update_zsku_category(rows, email):
    def get_categories():
        return sql(
            engine,
            '''
                    SELECT *
                    FROM boilerplate_catalog.category
                ''',
        ).dicts()

    categories = get_categories()
    code_to_id_category_map = {cat['code']: cat['id_category'] for cat in categories}

    rows_valid = [
        {"sku": row['zsku'], "id_category": code_to_id_category_map[row['category_code']], "email": email}
        for row in rows
        if code_to_id_category_map.get(row['category_code'])
    ]

    zskus = set()
    for row in rows_valid:
        zskus.add(row['sku'])

    zskus = list(zskus)
    zskus = [{"zsku": zsku} for zsku in zskus]
    if zskus:
        sqlutil.sqlmany(
            engine,
            '''
            DELETE FROM 
            boilerplate_catalog.product_category
            WHERE sku = :zsku
        ''',
            zskus,
        )

    if rows_valid:
        sqlutil.sqlmany(
            engine,
            '''
            INSERT INTO boilerplate_catalog.product_category (sku, id_category, updated_by)
            VALUES (:sku, :id_category, :email)
            ON DUPLICATE KEY UPDATE id_category=VALUES(id_category)
        ''',
            rows_valid,
        )

    publisher = pubsub.get_publisher('boilerplate_reindex_sku')
    zskus = [r['zsku'] for r in zskus]
    for chunk in iterutils.chunked(zskus, 500):
        publisher(json.dumps(chunk))


@register
def import_category_taxonomy(rows, email):
    def get_categories():
        return sql(
            engine,
            '''
                SELECT *
                FROM boilerplate_catalog.category
            ''',
        ).pk_map()

    def get_id_category_to_parent_ids_map(list_categories):
        rows = {category['id_category']: category['id_category_parent'] for category in list_categories}
        id_category_to_parent_ids_map = {}
        for id_category in rows.keys():
            all_parent_ids = []
            parent_id = rows.get(id_category)
            while parent_id is not None:
                all_parent_ids.append(parent_id)
                parent_id = rows.get(parent_id)
            id_category_to_parent_ids_map[id_category] = all_parent_ids + [id_category]
        return id_category_to_parent_ids_map

    categories = get_categories()
    id_category_to_parent_ids_map = get_id_category_to_parent_ids_map(list(categories.values()))

    # set `parent_code` attr for variable categories
    for id_category in categories:
        if categories[id_category]['id_category_parent']:
            id_category_parent = categories[id_category]['id_category_parent']
            categories[id_category]['parent_code'] = categories[id_category_parent]['code']
        else:
            categories[id_category]['parent_code'] = None

    # change list to dict where key is the `code`
    categories = {categories[id_category]['code']: categories[id_category] for id_category in categories}

    # remove entries with empty code
    rows = {r['code']: r for r in rows if r['code'] != ""}

    # find all categories whose parent is updated
    updated_category_ids = []
    for code in rows:
        if rows[code]['parent_code'] == '':
            rows[code]['parent_code'] = None
        if code in categories and categories[code]['parent_code'] != rows[code]['parent_code']:
            updated_category_ids.append(categories[code]['id_category'])

    # find all categories whose path to the root is changed
    affected_category_ids = []
    for code in categories:
        id_category = categories[code]['id_category']
        parent_ids = id_category_to_parent_ids_map[id_category]
        is_affected = False
        for parent_id in parent_ids:
            if parent_id in updated_category_ids:
                is_affected = True
                break
        if is_affected:
            affected_category_ids.append(id_category)

    # put all changes in categories variable
    for code in rows:
        categories[code] = rows[code]
        rows[code]['email'] = email

    # validate the tree hierachy
    for code in categories:
        visited = set()
        code_current = code
        while code_current:
            assert (
                code_current not in visited
            ), "category parent relationship forms a cycle. Please check the category relationship again"
            visited.add(code_current)
            if categories[code_current]['parent_code'] is not None:
                assert (
                    categories[code_current]['parent_code'] in categories
                ), f"parent of {code_current}: {categories[code_current]['parent_code']} does not exist"
            code_current = categories[code_current]['parent_code']

    # find all skus whose category_ids needs updating
    affected_skus = sql(
        engine,
        '''
        SELECT sku FROM boilerplate_catalog.product_category
        WHERE id_category IN :affected_category_id_list
    ''',
        affected_category_id_list=affected_category_ids,
    ).dicts()
    affected_skus = [r['sku'] for r in affected_skus]
    logger.warning(
        f"category update: affected skus are {affected_skus} affected category ids {affected_category_ids} updated category ids {updated_category_ids}"
    )

    # insert new categories
    sqlutil.sqlmany(
        engine,
        """
       INSERT INTO
          boilerplate_catalog.category (code, en_name, ar_name, updated_by) 
       VALUES (:code, :en_name, :ar_name, :email)
       ON DUPLICATE KEY UPDATE
          en_name = VALUES(en_name),
          ar_name = VALUES(ar_name),
          updated_by = VALUES(updated_by)
    """,
        list(rows.values()),
    )

    # get categories after insertion (useful to get the id_category values of the new catgories)
    categories = get_categories()
    code_to_id_category_map = {categories[id_category]['code']: id_category for id_category in categories}
    code_to_id_category_map[None] = None

    # update the id_category_parent
    for code in rows:
        rows[code]["id_category_parent"] = code_to_id_category_map[rows[code]['parent_code']]
    sqlutil.sqlmany(
        engine,
        """
       INSERT INTO
          boilerplate_catalog.category (code, id_category_parent, en_name, ar_name, updated_by) 
       VALUES (:code, :id_category_parent, :en_name, :ar_name, :email)
       ON DUPLICATE KEY UPDATE
          id_category_parent = VALUES(id_category_parent)
    """,
        list(rows.values()),
    )

    # publish skus for category sync
    publisher = pubsub.get_publisher('boilerplate_reindex_sku')
    for chunk in iterutils.chunked(affected_skus, 500):
        publisher(json.dumps(chunk))
