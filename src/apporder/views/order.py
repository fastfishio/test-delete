import logging

from fastapi import APIRouter

from apporder.web import g
from liborder import Context, domain

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post('/place', summary='Place order based on active session', tags=['order'])
@Context.fastapi_tx(attempts=3, tar_g=g)
def place_order(msg: domain.order.PlaceOrder):
    return msg.execute()


@router.post('/get', summary='Get order details', tags=['order'])
@Context.fastapi_tx(attempts=3, tar_g=g)
def get_order_details(msg: domain.order.GetDetails):
    # todo: optimize this call in GetDetails() itself
    #  so that you can get the payment status from order details
    domain.payment.refresh_payment_info_if_pending(order_nr=msg.order_nr)
    return msg.execute(local_tz=True)


@router.post('/list', summary='Get all orders details', tags=['order'])
@Context.fastapi_tx(attempts=3, tar_g=g)
def get_order_details(msg: domain.order.ListOrders):
    return msg.execute()


@router.post('/invoice', summary='Get invoice for order', tags=['order'])
@Context.fastapi_tx(attempts=3, tar_g=g)
def get_order_invoice(msg: domain.order.GetInvoice):
    return msg.execute()
