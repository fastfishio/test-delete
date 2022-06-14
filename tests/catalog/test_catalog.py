import pydantic
import pytest
from noonutil.v1 import storageutil

from tests.order.mocks.helpers import mock_read_from_cloud

storageutil.read_from_gcloud = mock_read_from_cloud


def test_search_suggestions(app_catalog):
    response = app_catalog.get('/suggestions?q=Milk')
    assert response.json() == {
        'brands': [],
        'categories': [],
        'products': [
            {
                'sku': 'Z019FDA9EAE0889BA47A9Z-1',
                'index': 1,
                'id_partner': 1,
                'title': 'Al Rawabi Milk ',
                'brand': 'Brand Code 1',
                'brand_code': 'brand_code1',
                'image_keys': ['ik1-Z019FDA9EAE0889BA47A9Z-1', 'ik2-Z019FDA9EAE0889BA47A9Z-1'],
                'image_key': 'ik1-Z019FDA9EAE0889BA47A9Z-1',
                'price': 5.7,
                'max_qty': 2,
                'sale_price': 5.65,
                'discount_percent': 0,
            },
            {
                'sku': 'Z019FDA9EAE0889BA47A9Z-1',
                'index': 2,
                'id_partner': 1,
                'title': 'Al Rawabi Milk ',
                'brand': 'Brand Code 1',
                'brand_code': 'brand_code1',
                'image_keys': ['ik1-Z019FDA9EAE0889BA47A9Z-1', 'ik2-Z019FDA9EAE0889BA47A9Z-1'],
                'image_key': 'ik1-Z019FDA9EAE0889BA47A9Z-1',
                'price': 15.9,
                'max_qty': 10,
                'sale_price': 15.65,
                'discount_percent': 1,
            }
        ],
        'suggestions': [],
        'facilities': [],
        'stores': [],
        'searchEngine': 'solr',
    }


def test_search_suggestions_short_query(app_catalog):
    response = app_catalog.get('/suggestions?q=Mi')
    assert response.json() == {
        'brands': [],
        'categories': [],
        'products': [],
        'suggestions': [],
        'facilities': [],
        'stores': [],
        'searchEngine': 'solr',
    }


def test_search_english(app_catalog, setup_spanner):
    response = app_catalog.get('/search?q=Milk')
    assert response.status_code == 200, f"Expected 200 status code: got {response.status_code}"
    rows = response.json()["results"][0]["modules"]
    assert len(rows) == 1
    data = rows[0]['products']
    assert len(data) == 2
    assert data[0] == {
        'sku': 'Z019FDA9EAE0889BA47A9Z-1',
        'title': 'Al Rawabi Milk ',
        'brand': 'Brand Code 1',
        'brand_code': 'brand_code1',
        'image_keys': ['ik1-Z019FDA9EAE0889BA47A9Z-1', 'ik2-Z019FDA9EAE0889BA47A9Z-1'],
        'id_partner': 1,
        'image_key': 'ik1-Z019FDA9EAE0889BA47A9Z-1',
        'index': 1,
        'price': 5.7,
        'sale_price': 5.65,
        'discount_percent': 0,
        'max_qty': 2,
    }


def test_search_product_carousel(app_catalog, setup_spanner):
    response = app_catalog.get('/search?q=Milk&productsOnly=1')
    assert response.status_code == 200, f"Expected 200 status code: got {response.status_code}"
    data = response.json()
    assert len(data['hits']) == 2
    assert data['hits'][0] == {
        'sku': 'Z019FDA9EAE0889BA47A9Z-1',
        'title': 'Al Rawabi Milk ',
        'brand': 'Brand Code 1',
        'index': 1,
        'brand_code': 'brand_code1',
        'id_partner': 1,
        'image_keys': ['ik1-Z019FDA9EAE0889BA47A9Z-1', 'ik2-Z019FDA9EAE0889BA47A9Z-1'],
        'image_key': 'ik1-Z019FDA9EAE0889BA47A9Z-1',
        'price': 5.7,
        'sale_price': 5.65,
        'max_qty': 2,
        'discount_percent': 0,
    }


def test_search_arabic(app_catalog, setup_spanner):
    response = app_catalog.get('/search?q=جامبو')
    assert response.status_code == 200, f"Expected 200 status code: got {response.status_code}"
    rows = response.json()["results"][0]["modules"]
    assert len(rows) == 2
    data = rows[0]['products']
    assert len(data) == 3
    assert data[1] == {
        'sku': 'Z019FDA9EAE0889BA47A9Z-1',
        'title': 'Al Rawabi Milk ',
        'brand': 'Brand Code 1',
        'brand_code': 'brand_code1',
        'id_partner': 1,
        'index': 2,
        'image_keys': ['ik1-Z019FDA9EAE0889BA47A9Z-1', 'ik2-Z019FDA9EAE0889BA47A9Z-1'],
        'image_key': 'ik1-Z019FDA9EAE0889BA47A9Z-1',
        'price': 5.7,
        'sale_price': 5.65,
        'max_qty': 2,
        'discount_percent': 0,
    }


def test_long_query_string_throws_validation_error(app_catalog):
    with pytest.raises(pydantic.error_wrappers.ValidationError):
        app_catalog.get('/search?q=asdfasdfasdfasdfsdafsdafasdfsadfsadfasdfasdfasdfasdfsadf')


def test_for_query_with_no_products(app_catalog, setup_spanner):
    response = app_catalog.get('/search?q=asdaddfdaf')
    assert response.status_code == 200, f"Expected 200 status code: got {response.status_code}"
    rows = response.json()["results"][0]["modules"]
    assert len(rows) == 0


def test_search_with_category_filter(app_catalog, setup_spanner):
    response = app_catalog.get('/search?f[category]=breakfast')
    assert response.status_code == 200, f"Expected 200 status code: got {response.status_code}"
    data = response.json()["results"][0]["modules"][0]["products"]
    assert len(data) == 3
    assert data == [
        {
            'sku': 'Z0174C34FC6F5FBDACC61Z-1',
            'title': 'Biosun Organic Bitter Cocoa Powder',
            'brand': 'Brand Code 2',
            'id_partner': 1,
            'index': 1,
            'brand_code': 'brand_code2',
            'image_keys': ['ik1-Z019FDA9EAE0889BA47A9Z-1', 'ik2-Z019FDA9EAE0889BA47A9Z-1'],
            'image_key': 'ik1-Z019FDA9EAE0889BA47A9Z-1',
            'price': 187,
            'sale_price': 107.65,
            'discount_percent': 42,
            'max_qty': 4,
        },
        {
            'sku': 'Z019FDA9EAE0889BA47A9Z-1',
            'title': 'Al Rawabi Milk ',
            'brand': 'Brand Code 1',
            'id_partner': 1,
            'brand_code': 'brand_code1',
            'index': 2,
            'image_keys': ['ik1-Z019FDA9EAE0889BA47A9Z-1', 'ik2-Z019FDA9EAE0889BA47A9Z-1'],
            'image_key': 'ik1-Z019FDA9EAE0889BA47A9Z-1',
            'price': 15.9,
            'sale_price': 15.65,
            'discount_percent': 1,
            'max_qty': 10,
        },
        {
            'sku': 'Z019FDA9EAE0889BA47A9Z-1',
            'title': 'Al Rawabi Milk ',
            'brand': 'Brand Code 1',
            'id_partner': 1,
            'brand_code': 'brand_code1',
            'index': 3,
            'image_keys': ['ik1-Z019FDA9EAE0889BA47A9Z-1', 'ik2-Z019FDA9EAE0889BA47A9Z-1'],
            'image_key': 'ik1-Z019FDA9EAE0889BA47A9Z-1',
            'price': 5.7,
            'sale_price': 5.65,
            'discount_percent': 0,
            'max_qty': 2,
        },
    ]


def test_search_with_sort(app_catalog, setup_spanner):
    response = app_catalog.get('/search?f[category]=breakfast&sort[by]=price&sort[dir]=desc')
    assert response.status_code == 200, f"Expected 200 status code: got {response.status_code}"
    data = response.json()["results"][0]["modules"][0]["products"]
    assert len(data) == 3
    assert data[0] == {
        'sku': 'Z0174C34FC6F5FBDACC61Z-1',
        'title': 'Biosun Organic Bitter Cocoa Powder',
        'brand': 'Brand Code 2',
        'index': 1,
        'brand_code': 'brand_code2',
        'id_partner': 1,
        'image_keys': ['ik1-Z019FDA9EAE0889BA47A9Z-1', 'ik2-Z019FDA9EAE0889BA47A9Z-1'],
        'image_key': 'ik1-Z019FDA9EAE0889BA47A9Z-1',
        'price': 187,
        'sale_price': 107.65,
        'discount_percent': 42,
        'max_qty': 4,
    }
    assert data[1] == {
        'sku': 'Z019FDA9EAE0889BA47A9Z-1',
        'title': 'Al Rawabi Milk ',
        'brand': 'Brand Code 1',
        'id_partner': 1,
        'brand_code': 'brand_code1',
        'index': 2,
        'image_keys': ['ik1-Z019FDA9EAE0889BA47A9Z-1', 'ik2-Z019FDA9EAE0889BA47A9Z-1'],
        'image_key': 'ik1-Z019FDA9EAE0889BA47A9Z-1',
        'price': 15.9,
        'sale_price': 15.65,
        'discount_percent': 1,
        'max_qty': 10,
    }
    assert data[2] == {
        'sku': 'Z019FDA9EAE0889BA47A9Z-1',
        'index': 3,
        'title': 'Al Rawabi Milk ',
        'brand': 'Brand Code 1',
        'brand_code': 'brand_code1',
        'id_partner': 1,
        'image_keys': ['ik1-Z019FDA9EAE0889BA47A9Z-1', 'ik2-Z019FDA9EAE0889BA47A9Z-1'],
        'image_key': 'ik1-Z019FDA9EAE0889BA47A9Z-1',
        'price': 5.7,
        'sale_price': 5.65,
        'discount_percent': 0,
        'max_qty': 2,
    }


def test_search_multiple_filters(app_catalog, setup_spanner):
    response = app_catalog.get('/search?q=Rawabi&f[price_min]=100&f[price_max]=200&sort[by]=price&sort[dir]=desc')
    assert response.status_code == 200, f"Expected 200 status code: got {response.status_code}"
    rows = response.json()["results"][0]["modules"]
    assert len(rows) == 1
    data = rows[0]['products']
    assert len(data) == 2
    assert data[0]['sale_price'] == 150.0
    assert data[1]['sale_price'] == 120.0


def test_search_multiple_filters_post(app_catalog, setup_spanner):
    params = {'q': 'Rawabi', 'f': {'price_min': [100.0], 'price_max': [200.0]}, 'sort': {'by': 'price', 'dir': 'desc'}}
    response = app_catalog.post('/search', json=params)
    assert response.status_code == 200, f"Expected 200 status code: got {response.status_code}"
    rows = response.json()["results"][0]["modules"]
    assert len(rows) == 1
    data = rows[0]['products']
    assert len(data) == 2
    assert data[0]['sale_price'] == 150.0
    assert data[1]['sale_price'] == 120.0


def test_pdp_happy(app_catalog, setup_spanner):
    data = {'sku': 'Z019FDA9EAE0889BA47A9Z-1'}
    response = app_catalog.post('/pdp', json=data)
    assert response.json() == {
        'sku': 'Z019FDA9EAE0889BA47A9Z-1',
        'title': 'Al Rawabi Milk ',
        'brand': 'Brand Code 1',
        'id_partner': 1,
        'brand_code': 'brand_code1',
        'is_buyable': True,
        'image_keys': ['ik1-Z019FDA9EAE0889BA47A9Z-1', 'ik2-Z019FDA9EAE0889BA47A9Z-1'],
        'image_key': 'ik1-Z019FDA9EAE0889BA47A9Z-1',
        'price': 5.7,
        'sale_price': 5.65,
        'discount_percent': 0,
        'max_qty': 2,
    }


def test_pdp_wrong_sku(app_catalog, setup_spanner):
    data = {'sku': 'ZWW9FDA9EAE0889BA47A9Z-1'}
    response = app_catalog.post('/pdp', json=data)
    assert response.status_code == 404


def test_brand_search(app_catalog, setup_spanner):
    response = app_catalog.get('/search?q=iphone&productsOnly=1')
    assert response.json() == {
        'hits': [
            {
                'sku': 'Z019FDA9EAE0889BA47A9Z-1',
                'title': 'Al Rawabi Milk ',
                'brand': 'Brand Code 1',
                'id_partner': 1,
                'brand_code': 'brand_code1',
                'index': 1,
                'image_keys': ['ik1-Z019FDA9EAE0889BA47A9Z-1', 'ik2-Z019FDA9EAE0889BA47A9Z-1'],
                'image_key': 'ik1-Z019FDA9EAE0889BA47A9Z-1',
                'price': 5.7,
                'sale_price': 5.65,
                'discount_percent': 0,
                'max_qty': 2,
            },
            {
                'sku': 'Z019FDA9EAE0889BA47A9Z-1',
                'title': 'Al Rawabi Milk ',
                'brand': 'Brand Code 1',
                'id_partner': 1,
                'brand_code': 'brand_code1',
                'index': 2,
                'image_keys': ['ik1-Z019FDA9EAE0889BA47A9Z-1', 'ik2-Z019FDA9EAE0889BA47A9Z-1'],
                'image_key': 'ik1-Z019FDA9EAE0889BA47A9Z-1',
                'price': 15.9,
                'sale_price': 15.65,
                'discount_percent': 1,
                'max_qty': 10,
            },
            {
                'sku': 'ZG19FDA9EAE0889BA47A9Z-1',
                'index': 3,
                'title': 'Al Rawabi  ',
                'brand': 'Brand Code 1',
                'id_partner': 1,
                'brand_code': 'brand_code1',
                'image_keys': ['ik1-Z019FDA9EAE0889BA47A9Z-1', 'ik2-Z019FDA9EAE0889BA47A9Z-1'],
                'image_key': 'ik1-Z019FDA9EAE0889BA47A9Z-1',
                'price': 200,
                'sale_price': 120,
                'discount_percent': 40,
                'max_qty': 2,
            },
        ]
    }


def test_search_with_brand_filter(app_catalog, setup_spanner):
    response = app_catalog.get('/search?f[brand]=my_brand_test_2&productsOnly=1')
    assert response.json() == {
        'hits': [
            {
                'sku': 'ZG19FDA9EAE0889BA47A9Z-1',
                'title': 'Al Rawabi  ',
                'brand': 'Brand Code 1',
                'id_partner': 1,
                'brand_code': 'brand_code1',
                'index': 1,
                'image_keys': ['ik1-Z019FDA9EAE0889BA47A9Z-1', 'ik2-Z019FDA9EAE0889BA47A9Z-1'],
                'image_key': 'ik1-Z019FDA9EAE0889BA47A9Z-1',
                'price': 200,
                'sale_price': 120,
                'discount_percent': 40,
                'max_qty': 2,
            },
            {
                'sku': 'ZU19FDA9EAE0889BA47A9Z-1',
                'index': 2,
                'title': 'Al Rawabi  ',
                'brand': 'Brand Code 1',
                'id_partner': 1,
                'brand_code': 'brand_code1',
                'image_keys': ['ik1-Z019FDA9EAE0889BA47A9Z-1', 'ik2-Z019FDA9EAE0889BA47A9Z-1'],
                'image_key': 'ik1-Z019FDA9EAE0889BA47A9Z-1',
                'price': 250,
                'sale_price': 150,
                'discount_percent': 40,
                'max_qty': 1,
            },
            {
                'sku': 'ZT19FDA9EAE0889BA47A9Z-1',
                'index': 3,
                'title': 'Al Rawabi  ',
                'brand': 'Brand Code 1',
                'id_partner': 1,
                'brand_code': 'brand_code1',
                'image_keys': ['ik1-Z019FDA9EAE0889BA47A9Z-1', 'ik2-Z019FDA9EAE0889BA47A9Z-1'],
                'image_key': 'ik1-Z019FDA9EAE0889BA47A9Z-1',
                'price': 300,
                'sale_price': 230,
                'discount_percent': 23,
                'max_qty': 2,
            },
        ]
    }


def test_empty_search_return_homepage_get(app_catalog):
    response = app_catalog.get('/search')
    assert response.json()['results'][0]['modules'][0]['type'] == 'bannerModuleStrip'


def test_empty_search_return_homepage_post(app_catalog):
    response = app_catalog.post('/search', json={})
    assert response.json()['results'][0]['modules'][0]['type'] == 'bannerModuleStrip'


def test_navpills_search(app_catalog):
    response = app_catalog.get('/search?f[category]=oil', json={})
    assert response.json()['navPills'] == []
    assert response.json()['facets'] == []
    response = app_catalog.get('/search?f[category]=oil&f[category]=dairy', json={})
    assert response.json()['navPills'] == [
        {
            'name': 'cat2',
            'filterName': 'Category',
            'filter': 'facets',
            'isSticky': True,
            'isSingleSelection': True,
            'code': 'category',
            'isSelected': True,
        },
        {
            'name': 'cat3',
            'filter': 'category',
            'isSingleSelection': True,
            'parentCode': 'dairy',
            'code': 'milk',
            'isSelected': False,
        },
        {
            'name': 'cat4',
            'filter': 'category',
            'isSingleSelection': True,
            'parentCode': 'dairy',
            'code': 'oil',
            'isSelected': True,
        },
    ]
    assert response.json()['facets'] == [
        {
            'code': 'category',
            'name': 'Category',
            'type': 'category',
            'data': [
                {'name': 'cat2', 'code': 'breakfast', 'count': 1, 'children': [], 'isSelected': False},
                {
                    'name': 'cat2',
                    'code': 'dairy',
                    'count': 1,
                    'children': [
                        {'name': 'cat3', 'code': 'milk', 'count': 1, 'children': [], 'isSelected': False},
                        {'name': 'cat4', 'code': 'oil', 'count': 1, 'children': [], 'isSelected': True},
                    ],
                    'isSelected': True,
                },
            ],
        }
    ]
    response = app_catalog.get('/search?f[category]=dairy', json={})
    assert response.json()['navPills'] == [
        {
            'name': 'cat2',
            'filterName': 'Category',
            'filter': 'facets',
            'isSticky': True,
            'isSingleSelection': True,
            'code': 'category',
            'isSelected': True,
        },
        {
            'name': 'cat3',
            'filter': 'category',
            'isSingleSelection': True,
            'parentCode': 'dairy',
            'code': 'milk',
            'isSelected': False,
        },
        {
            'name': 'cat4',
            'filter': 'category',
            'isSingleSelection': True,
            'parentCode': 'dairy',
            'code': 'oil',
            'isSelected': False,
        },
    ]
    assert response.json()['facets'] == [
        {
            'code': 'category',
            'name': 'Category',
            'type': 'category',
            'data': [
                {'name': 'cat2', 'code': 'breakfast', 'count': 1, 'children': [], 'isSelected': False},
                {
                    'name': 'cat2',
                    'code': 'dairy',
                    'count': 1,
                    'children': [
                        {'name': 'cat3', 'code': 'milk', 'count': 1, 'children': [], 'isSelected': False},
                        {'name': 'cat4', 'code': 'oil', 'count': 1, 'children': [], 'isSelected': False},
                    ],
                    'isSelected': True,
                },
            ],
        }
    ]
    response = app_catalog.get('/search?q=Rawabi&f[category]=dairy', json={})
    assert response.json()['navPills'] == []
    assert response.json()['facets'] == []
