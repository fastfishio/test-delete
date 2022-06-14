from libcatalog.domain.category import *


def test_get_parent_categories():
    sku_list = ['Z7BE12221F4AE467439A0Z-1', 'Z7BE12221F4AE467439A1Z-1']
    id_category_list = [row['id_category'] for row in get_id_categories_for(sku_list) if row['sku'] == 'Z7BE12221F4AE467439A0Z-1']
    assert len(id_category_list) == 1
    id_category = id_category_list[0]
    assert id_category == 3
    assert set(get_id_category_to_parent_ids_map().get(id_category)) == {3, 2}
    id_category_list = [row['id_category'] for row in get_id_categories_for(sku_list) if row['sku'] == 'Z7BE12221F4AE467439A1Z-1']
    assert len(id_category_list) == 1
    id_category = id_category_list[0]
    assert id_category == 4
    assert set(get_id_category_to_parent_ids_map().get(id_category)) == {4, 2}
