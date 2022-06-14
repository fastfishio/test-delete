import logging
from typing import List

from fastapi import APIRouter

from appcs.web import g
from libcs import domain
from libcs.models import dtos
from liborder import Context

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post('/details', summary='Get order details for CS', tags=['order'], response_model=dtos.CSOrder)
def get_cs_order_details(msg: domain.customer_service.GetDetails):
    with Context.fastapi(tar_g=g):
        return msg.execute()


@router.post('/comment/add', summary='Add comment on order', tags=['comment'], response_model=dtos.CSOrder)
def add_comment(msg: domain.customer_service.AddComment):
    with Context.fastapi(tar_g=g):
        msg.execute()
        return domain.customer_service.GetDetails(order_nr=msg.order_nr).execute()


@router.post('/comment/edit', summary='Edit comment on order', tags=['comment'], response_model=dtos.CSOrder)
def edit_comment(msg: domain.customer_service.EditComment):
    with Context.fastapi(tar_g=g):
        msg.execute()
        return domain.customer_service.GetDetails(order_nr=msg.order_nr).execute()


@router.post('/comment/delete', summary='Delete comment on order', tags=['comment'], response_model=dtos.CSOrder)
def delete_comment(msg: domain.customer_service.DeleteComment):
    with Context.fastapi(tar_g=g):
        msg.execute()
        return domain.customer_service.GetDetails(order_nr=msg.order_nr).execute()


@router.post('/adjustment/add', summary='Add Adjustment on order', tags=['order'], response_model=dtos.CSOrder)
def add_adjustment(msg: domain.customer_service.AddAdjustment):
    with Context.fastapi(tar_g=g):
        msg.execute()
        return domain.customer_service.GetDetails(order_nr=msg.order_nr).execute()


@router.post(
    '/adjustment/reasons',
    summary='Get adjustment reasons',
    tags=['order'],
    response_model=List[dtos.CSAdjustmentReason],
)
def add_adjustment():
    with Context.fastapi(tar_g=g):
        return domain.customer_service.get_adjustment_reasons()


@router.post('/issue-credit', summary='Issue Goodwill credits', tags=['credit'], response_model=dtos.CSOrder)
def issue_credit(msg: domain.customer_service.IssueCredit):
    with Context.fastapi(tar_g=g):
        msg.execute()
        return domain.customer_service.GetDetails(order_nr=msg.order_nr).execute()


@router.post('/cancel', summary='Cancel Order', tags=['order'], response_model=dtos.CSOrder)
def cancel(msg: domain.customer_service.CancelOrder):
    with Context.fastapi(tar_g=g):
        msg.execute()
        return domain.customer_service.GetDetails(order_nr=msg.order_nr).execute()


@router.get('/cancel-reasons', summary='Get Cancel Reasons', tags=['order'], response_model=List[dtos.CancelReason])
def get_cancel_reasons():
    with Context.fastapi(tar_g=g):
        return domain.customer_service.get_cancel_reasons()


@router.post('/search', tags=['order'], response_model=dtos.SearchResult)
def search(msg: domain.customer_service.Search):
    with Context.fastapi(tar_g=g):
        return msg.execute()


@router.post('/whoami', tags=['user'], response_model=dtos.CSUser)
def whoami(msg: domain.customer_service.WhoAmI):
    with Context.fastapi(tar_g=g):
        return msg.execute()
