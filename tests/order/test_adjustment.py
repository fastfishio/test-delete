from libcs.domain import customer_service
from liborder import Context
from liborder.domain import order
from liborder.domain.enums import Status
from tests.order import util as testutil
from libutil import util

WH2_LAT = 252005240
WH2_LNG = 552807372
WH3_LAT = 252105240
WH3_LNG = 552817372


def test_adjustments():
    with Context.service(visitor_id="v1", customer_code="c1", lat=WH2_LAT, lng=WH2_LNG, address_key='A091-1'):
        _, order_nr = testutil.place_order(items=[('Z019FDA9EAE0889BA47A1Z-1', 1)], payment_method_code='cod')
    # mock order to be delivered
    with Context.service():
        order.modify_order(order_nr, {'status_code_order': Status.DELIVERED.value}, internal=True)
        order_details = order.GetDetails(order_nr=order_nr).execute(internal=True)
        assert order_details.status_code == 'delivered'

    # adjustment stuff starts from here
    with Context.service(user_code='cs_leader@noon.com'):
        customer_service.AddAdjustment(reason_code='shipping_fee_refund', order_nr=order_nr).execute()
        order_details = order.GetDetails(order_nr=order_nr).execute(internal=True)
        assert order_details.order_mp_adjustment == -10
        assert util.equal_decimals(order_details.order_collect_from_customer, 2.65)

    with Context.service(user_code='cs_leader@noon.com'):
        customer_service.AddAdjustment(reason_code='missing_item', order_nr=order_nr, item_nr=order_nr + "-1").execute()
        order_details = order.GetDetails(order_nr=order_nr).execute(internal=True)
        assert util.equal_decimals(order_details.order_mp_adjustment, -12.65)
        assert util.equal_decimals(order_details.order_collect_from_customer, 0)
    # now, say you add adjustment for the same item again, for a different reason
    #  the adjustment amount won't change, but the reason would, so basically one adjustment per item
    with Context.service(user_code='cs_leader@noon.com'):
        customer_service.AddAdjustment(
            reason_code='bad_quality_item', order_nr=order_nr, item_nr=order_nr + "-1"
        ).execute()
        order_details = order.GetDetails(order_nr=order_nr).execute(internal=True)
        assert util.equal_decimals(order_details.order_mp_adjustment, -12.65)
        assert util.equal_decimals(order_details.order_collect_from_customer, 0)

    with Context.service(user_code='cs_leader@noon.com'):
        adjustments = customer_service.get_order_adjustments(order_nr, 'AED')
        assert len(adjustments) == 2
        assert adjustments[0].item_nr == ''
        assert adjustments[0].amount == "-10.00 AED"
        assert adjustments[0].user_code == "cs_leader@noon.com"
        assert adjustments[0].reason_code == 'shipping_fee_refund'

        assert adjustments[1].amount == "-2.65 AED"
        assert adjustments[1].item_nr == f"{order_nr}-1"
        assert adjustments[1].user_code == "cs_leader@noon.com"
        assert adjustments[1].reason_code == 'bad_quality_item'
