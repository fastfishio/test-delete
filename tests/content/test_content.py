import datetime

from noonutil.v1 import storageutil

from tests.order.mocks.helpers import mock_read_from_cloud

storageutil.read_from_gcloud = mock_read_from_cloud

EARLY_MORNING = datetime.datetime(2020, 12, 25, 3, 30, 0)
LATE_NIGHT = datetime.datetime(2020, 12, 25, 19, 0, 0)

servicable_loc_headers = {
    "x-lat": "251944818",
    "x-lng": "552744380"
}


class EarlyMorning(datetime.datetime):
    def now():
        return EARLY_MORNING


class LateNight(datetime.datetime):
    def now():
        return LATE_NIGHT


def test_content_in_early_morning(app_catalog, monkeypatch):
    monkeypatch.setattr(datetime, 'datetime', EarlyMorning)
    response = app_catalog.get('/home', headers=servicable_loc_headers)
    results = response.json()['results']
    assert results == [{
        'modules': [{
            'type': 'bannerModuleStrip',
            'widgetCode': 'widget_1',
            'numPerRow': '5',
            'moduleHeader': {
                'titleText': 'hellllooo',
                'titleColor': None
            },
            'banners': [{
                'code': 'asset_5',
                'linkUrl': 'mylink',
                'imageUrl': 'https://storage.googleapis.com/noonstg-mp-gcs-boilerplate-cms/image_link'
            },
                {
                    'code': 'asset_2',
                    'linkUrl': 'mylink_2',
                    'imageUrl': 'https://storage.googleapis.com/noonstg-mp-gcs-boilerplate-cms/image_link'
                }
            ],
            'inner_spacing': 5,
            'outer_spacing': {
                'top': 0,
                'bottom': 5
            }
        }]
    }, {
        'modules': [{
            'type': 'bannerSlider',
            'widgetCode': 'widget_3',
            'numPerRow': '2',
            'moduleHeader': {
                'titleText': 'english title',
                'titleColor': None
            },
            'banners': [
                {
                    'code': 'early_in_the_morning',
                    'linkUrl': 'mylink_2',
                    'imageUrl': 'https://storage.googleapis.com/noonstg-mp-gcs-boilerplate-cms/image_link'
                }
            ]
        }]
    }, {
        'modules': [{
            'type': 'productCarousel',
            'widgetCode': 'widget_2',
            'productUrl': '/search?q=water&productsOnly=1',
            'moduleHeader': {
                'titleText': 'english title',
                'titleColor': None,
                'linkUrl': '/search?q=water',
                'linkText': 'VIEW ALL'
            }
        }]
    }, {
        'modules': [{
            'type': 'productList',
            'widgetCode': 'widget_5',
            'productUrl': '/search?q=water&productsOnly=1',
            'moduleHeader': {
                'titleText': '',
                'titleColor': None
            },
            'showAllURL': '/search?q=water',
            'initialNum': 20
        }]
    }]
