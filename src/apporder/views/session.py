import logging

from fastapi import APIRouter

from apporder.web import g
from liborder import Context, domain

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post('/get', summary='get active session', tags=['session'])
@Context.fastapi_tx(attempts=3, tar_g=g)
def get_active_session(msg: domain.session.GetOrCreate):
    return msg.execute()


@router.post('/item/add', summary='Add item to active session', tags=['session'])
@Context.fastapi_tx(attempts=3, tar_g=g)
def add_item(msg: domain.session.AddItem):
    return msg.execute()


@router.post('/item/set-qty', summary='Set item qty in active session', tags=['session'])
@Context.fastapi_tx(attempts=3, tar_g=g)
def set_quantity(msg: domain.session.SetQuantity):
    return msg.execute()


@router.post('/item/remove', summary='Remove item from active session', tags=['session'])
@Context.fastapi_tx(attempts=3, tar_g=g)
def remove_item(msg: domain.session.RemoveItem):
    return msg.execute()


@router.post('/delivery-preferences/set', summary='Set delivery preferences for active session', tags=['session'])
@Context.fastapi_tx(attempts=3, tar_g=g)
def set_delivery_preferences(msg: domain.session.SetDeliveryPreferences):
    return msg.execute()


@router.post('/payment-method/set', summary='Set payment method for active session', tags=['session'])
@Context.fastapi_tx(attempts=3, tar_g=g)
def set_payment_method(msg: domain.session.SetPaymentMethod):
    return msg.execute()


@router.post('/payment-method/reset', summary='Set payment method for active session', tags=['session'])
@Context.fastapi_tx(attempts=3, tar_g=g)
def set_payment_method(msg: domain.session.ResetPaymentMethod):
    return msg.execute()


@router.post('/reset', summary='Reset the checkout session', tags=['session'])
@Context.fastapi_tx(attempts=3, tar_g=g)
def reset_checkout_session(msg: domain.session.ResetCheckoutSession):
    msg.execute()
    return domain.session.GetOrCreate(refresh=True).execute()
