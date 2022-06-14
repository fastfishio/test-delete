from datetime import datetime

import pytest
import pytz
from tests.order import util as testutil
from libcs.domain import customer_service
from liborder import Context

WH2_LAT = 252005240
WH2_LNG = 552807372
WH3_LAT = 252105240
WH3_LNG = 552817372


def test_get_cs_order(data_order):
    with Context.service(visitor_id="v1", customer_code="c1", lat=WH2_LAT, lng=WH2_LNG, address_key='A091-1'):
        session, order_nr = testutil.place_order(items=[('Z019FDA9EAE0889BA47A1Z-1', 1)], payment_method_code='cod')

    with Context.service(user_code='cs_leader@noon.com'):
        cs_details = customer_service.GetDetails(order_nr=order_nr).execute()
        assert cs_details.customer_code == 'c1', 'Invalid customer code'
        assert cs_details.order_status == 'Confirmed', 'Invalid order status'
        assert cs_details.order_status_code == 'confirmed', 'Invalid status code'
        assert cs_details.warehouse_details[0].value == 'WH2', 'Invalid warehouse code'
        assert cs_details.warehouse_details[1].value.lower() == 'ae', 'Invalid country code'
        assert cs_details.warehouse_details[2].value == 'Dubai', 'Invalid city'
        assert cs_details.warehouse_details[3].value == 'Downtown', 'Invalid area'
        customer_service.IssueCredit(order_nr=order_nr, amount=10, reason='Its not real money so why not?').execute()
        customer_service.IssueCredit(order_nr=order_nr, amount=11, reason='Its not real money so why not?').execute()
        cs_details = customer_service.GetDetails(order_nr=order_nr).execute()
        assert len(cs_details.action_log) == 2, 'Invalid number of entries in action log'
        assert cs_details.action_log[0].user_code == 'cs_leader@noon.com'
        assert cs_details.action_log[0].msg == f'Issued credits set to AED 10.00.'
        assert cs_details.action_log[0].reason == 'Its not real money so why not?'
        assert cs_details.action_log[1].msg == f'Issued credits set to AED 11.00.'
        assert cs_details.action_log[1].reason == 'Its not real money so why not?'

        cs_search = customer_service.Search(query='%').execute()
        assert order_nr in [order['order_nr'] for order in cs_search.orders]
