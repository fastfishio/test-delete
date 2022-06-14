from tests.order import util as testutil
from libcs.domain import customer_service
from liborder import Context
import pytest

WH2_LAT = 252005240
WH2_LNG = 552807372


def test_access(app_team, app_cs):

    # test domain
    with Context.service(
        visitor_id="v1",
        customer_code="c1",
        lat=WH2_LAT,
        lng=WH2_LNG,
        address_key='A091-1',
        user_code='cs_leader@noon.com',
    ):
        session, order_nr = testutil.place_order(items=[('Z019FDA9EAE0889BA47A1Z-1', 1)], payment_method_code='cod')
        cs_details = customer_service.GetDetails(order_nr=order_nr).execute()
        customer_service.IssueCredit(order_nr=order_nr, amount=10, reason='Its not real money so why not?').execute()
        customer_service.IssueCredit(order_nr=order_nr, amount=11, reason='Its not real money so why not?').execute()
        cs_details = customer_service.GetDetails(order_nr=order_nr).execute()

    with Context.service(user_code='cs_empty@noon.com'):
        with pytest.raises(AssertionError, match=r"Permission denied.*"):
            cs_order = customer_service.GetDetails(order_nr=order_nr).execute()

    with Context.service(user_code='platform_admin@noon.com'):
        cs_order = customer_service.GetDetails(order_nr=order_nr).execute()

    with Context.service(user_code='cs_agent@noon.com'):
        with pytest.raises(
            AssertionError,
            match=f'Permission denied: user CS_AGENT@NOON.COM does not have permission CS_ISSUE_CREDIT on CUSTOMER_SERVICE resource .*',
        ):
            customer_service.IssueCredit(order_nr=order_nr, amount=1, reason='Its not real money so why not?').execute()

    # test views
    res = app_cs.post(
        '/details', json={'order_nr': order_nr}, headers={'x-forwarded-user': "cs_leader@noon.com"}
    ).json()
    assert res['orderNr'] == order_nr

    res = app_cs.post('/details', json={'order_nr': order_nr}, headers={'x-forwarded-user': "cs_empty@noon.com"}).json()
    assert res['error'].startswith(
        'Permission denied: user CS_EMPTY@NOON.COM does not have permission CS_ORDER_DETAILS on CUSTOMER_SERVICE resource'
    )
