from typing import List, Dict

from jsql import sql
from noonutil.v1 import miscutil

from libcatalog import engine
from libcatalog.models.category import Category


def _get_category_table() -> List[Category]:
    rows = sql(
        engine,
        '''
                SELECT *
                FROM boilerplate_catalog.category
            ''',
    ).dicts()
    return [Category(**row) for row in rows]


@miscutil.cached(ttl=60 * 60)
def _get_category_table_cached() -> List[Category]:
    return _get_category_table()


def get_category_list(cached: bool = True) -> List[Category]:
    if cached:
        return _get_category_table_cached()
    else:
        return _get_category_table()


def get_code_to_id_category_map(cached: bool = True) -> Dict[str, int]:
    return {category.code: category.id_category for category in get_category_list(cached=cached)}


def get_id_category_to_category_map(cached: bool = True) -> Dict[id, Category]:
    id_category_to_category_map = {category.id_category: category for category in get_category_list(cached=cached)}

    for id_category, category in id_category_to_category_map.items():
        category.children = []
        if category.id_category_parent:
            id_category_to_category_map[category.id_category_parent].children.append(id_category)

    return id_category_to_category_map


def get_id_category_to_category_map_for_root_categories(cached: bool = True):
    id_category_to_category_map = get_id_category_to_category_map(cached)
    return {
        id_category: category
        for id_category, category in id_category_to_category_map.items()
        if not category.id_category_parent
    }


def get_id_category_to_parent_ids_map(cached: bool = True):
    rows = {category.id_category: category.id_category_parent for category in get_category_list(cached=cached)}
    id_category_to_parent_ids_map = {}
    for id_category in rows.keys():
        all_parent_ids = []
        parent_id = rows.get(id_category)
        while parent_id is not None:
            all_parent_ids.append(parent_id)
            parent_id = rows.get(parent_id)
        id_category_to_parent_ids_map[id_category] = all_parent_ids + [id_category]
    return id_category_to_parent_ids_map


def get_id_categories_for(sku_list):
    return sql(
        engine,
        '''
                SELECT sku, id_category 
                FROM boilerplate_catalog.product_category
                WHERE sku IN :sku_list
            ''',
        sku_list=sku_list,
    ).dicts()


def get_sku_group_code_map_for(sku_list):
    return sql(
        engine,
        '''
                SELECT sku, group_code 
                FROM boilerplate_catalog.product_group_code
                WHERE sku IN :sku_list
            ''',
        sku_list=sku_list,
    ).kv_map()
