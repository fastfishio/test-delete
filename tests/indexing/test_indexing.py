from datetime import datetime

import pytz
from dateutil.relativedelta import relativedelta
from jsql import sql

from libindexing.domain import product
from libindexing.domain.price import reindex_price
from libindexing.domain.stock import reindex_stock
from libutil.spanner_util import boilerplate_spanner, noon_cache_spanner
from tests.indexing.mocks import product as mocked_product


def test_price_update(data_indexing, setup_spanner):
    reindex_price([('Z008431D8F223B31EF128Z-1', 'WH2')])
    spanner_offer_row = boilerplate_spanner().execute_sql('''
                    SELECT sku, offer_price, msrp, updated_at
                    FROM offer
                    WHERE sku = 'Z008431D8F223B31EF128Z-1'
                    AND wh_code = 'WH2'
                ''').dict()
    assert spanner_offer_row['sku'] == 'Z008431D8F223B31EF128Z-1'
    assert spanner_offer_row['offer_price'] == 105
    # this is just to make sure that the price was updated recently because of reindexing
    assert spanner_offer_row['updated_at'] >= datetime.now(tz=pytz.UTC) - relativedelta(seconds=10)


def test_stock_update_product_data_exist(engine_offer, monkeypatch):
    reindex_stock([{
        "psku_code": "abcde",
        "warehouse_code": "WH2"
    }])
    offer_stock_row = sql(engine_offer, '''
        SELECT stock_net
        FROM offer_stock
        WHERE sku = :sku
        AND wh_code = :wh_code
    ''', sku="Z008431D8F223B31EF128Z-1", wh_code="WH2").dict()

    assert offer_stock_row["stock_net"] == 26
    spanner_offer_stock_row = boilerplate_spanner().execute_sql('''
                    SELECT stock_net
                    FROM offer_stock
                    WHERE sku = 'Z008431D8F223B31EF128Z-1'
                    AND wh_code = 'WH2'
                ''').dict()
    assert spanner_offer_stock_row['stock_net'] == 26


def test_stock_update_product_data_new_from_zsku(engine_offer, monkeypatch):
    # taking sku which doesn't have product data loaded
    monkeypatch.setattr(product, 'fetch_nsku_details', mocked_product.mock_fetch_nsku_details)
    monkeypatch.setattr(product, 'fetch_zsku_details', mocked_product.mock_fetch_zsku_details)
    reindex_stock([{
        "psku_code": "lemon",
        "warehouse_code": "WH2"
    }])
    offer_stock_row = sql(engine_offer, '''
        SELECT stock_net
        FROM offer_stock
        WHERE sku = :sku
        AND wh_code = :wh_code
    ''', sku="Z111111111112Z-1", wh_code="WH2").dict()

    assert offer_stock_row["stock_net"] == 8566
    spanner_offer_stock_row = boilerplate_spanner().execute_sql('''
                    SELECT stock_net
                    FROM offer_stock
                    WHERE sku = 'Z111111111112Z-1'
                    AND wh_code = 'WH2'
                ''').dict()
    assert spanner_offer_stock_row['stock_net'] == 8566
    spanner_product_row = boilerplate_spanner().execute_sql('''
                    SELECT family_code
                    FROM product
                    WHERE sku = 'Z111111111112Z-1'
                ''').dict()
    assert spanner_product_row['family_code'] == "test my way"
    spanner_product_en_row = boilerplate_spanner().execute_sql('''
                    SELECT title
                    FROM product_en
                    WHERE sku = 'Z111111111112Z-1'
                ''').dict()
    assert spanner_product_en_row['title'] == "title test good luck"


def test_stock_update_product_data_new_from_nsku(engine_offer, monkeypatch):
    # taking sku which doesn't have product data loaded
    monkeypatch.setattr(product, 'fetch_nsku_details', mocked_product.mock_fetch_nsku_details)
    monkeypatch.setattr(product, 'fetch_zsku_details', mocked_product.mock_fetch_zsku_details)
    reindex_stock([{
        "psku_code": "aaaa",
        "warehouse_code": "WH2"
    }])
    offer_stock_row = sql(engine_offer, '''
        SELECT stock_net
        FROM offer_stock
        WHERE sku = :sku
        AND wh_code = :wh_code
    ''', sku="Z111111111111Z-1", wh_code="WH2").dict()

    assert offer_stock_row["stock_net"] == 10
    spanner_offer_stock_row = boilerplate_spanner().execute_sql('''
                    SELECT stock_net
                    FROM offer_stock
                    WHERE sku = 'Z111111111111Z-1'
                    AND wh_code = 'WH2'
                ''').dict()
    assert spanner_offer_stock_row['stock_net'] == 10
    spanner_product_row = boilerplate_spanner().execute_sql('''
                    SELECT family_code, group_code
                    FROM product
                    WHERE sku = 'Z111111111111Z-1'
                ''').dict()
    assert spanner_product_row['family_code'] == "sports_outdoor"
    assert spanner_product_row['group_code'] == "group2"
    spanner_product_en_row = boilerplate_spanner().execute_sql('''
                    SELECT title
                    FROM product_en
                    WHERE sku = 'Z111111111111Z-1'
                ''').dict()
    assert spanner_product_en_row['title'] == "Hex Dumbbell 5kg"


def test_boilerplate_stock_logic():
    reindex_stock([{
        "psku_code": "gg",
        "warehouse_code": "WH2"
    }])

    row = noon_cache_spanner().execute_sql('''
            SELECT *
            FROM boilerplate_stock
            WHERE sku = 'N12345' and wh_code = 'WH2'
        ''').dict()
    assert not row, "the row didn't get deleted"

    row = noon_cache_spanner().execute_sql('''
            SELECT *
            FROM boilerplate_stock
            WHERE sku = 'N12345' and wh_code = 'WH3'
        ''').dict()
    assert row, "wrong wh_code got deleted"

    row = noon_cache_spanner().execute_sql('''
            SELECT *
            FROM boilerplate_stock
            WHERE sku = 'Z12345-1' AND wh_code = 'WH2' AND stock_net = 7788
        ''').dict()
    assert row, "the row didn't get inserted"

    reindex_stock([{
        "psku_code": "hh",
        "warehouse_code": "WH2"
    }])

    row = noon_cache_spanner().execute_sql('''
            SELECT *
            FROM boilerplate_stock
            WHERE sku = 'N11111' AND wh_code = 'WH2' AND stock_net = 1234
        ''').dict()
    assert row, "the row didn't get inserted"

    reindex_stock([{
        "psku_code": "tt",
        "warehouse_code": "WH2"
    }])

    row = noon_cache_spanner().execute_sql('''
            SELECT *
            FROM boilerplate_stock
            WHERE sku = 'Z22222-1' AND wh_code = 'WH2' AND stock_net = 2345
        ''').dict()
    assert row, "the row didn't get inserted"

    row = noon_cache_spanner().execute_sql('''
            SELECT *
            FROM boilerplate_stock
            WHERE sku = 'N22222' AND wh_code = 'WH2'
        ''').dict()
    assert not row, "the row should not have been inserted"
