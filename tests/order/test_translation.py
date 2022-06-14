from liborder import Context, domain
from libexternal import customer
from tests.order.mocks import customer as mocked_customer
from tests.order import util as testutil

WH2_LAT = 252005240
WH2_LNG = 552807372
WH3_LAT = 252105240
WH3_LNG = 552817372


def test_translation(monkeypatch):
    with Context.service(visitor_id="v1", customer_code="c1", lat=WH2_LAT, lng=WH2_LNG, address_key='A091-1'):
        session, order_nr = testutil.place_order(items=[('Z019FDA9EAE0889BA47A1Z-1', 2)], payment_method_code='cod')
    with Context.service(visitor_id="v1", customer_code="c1", lat=WH2_LAT, lng=WH2_LNG, lang='ar', address_key='A091-1'):
        order_details = domain.order.GetDetails(order_nr=order_nr).execute()
        assert order_details.country_code == 'AE'
        assert order_details.status_code == 'confirmed'
        assert order_details.status == 'مؤكد'
