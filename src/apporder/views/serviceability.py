import logging

from fastapi import APIRouter

from apporder.web import g
from liborder import Context, domain

logger = logging.getLogger(__name__)
router = APIRouter()


# this would be called by FE on pin selection by user
# move to a separate service? or to catalog?
@router.post('/get', summary='Get serviceability', tags=['serviceability'])
@Context.fastapi_tx(attempts=3, tar_g=g)
def get_serviceability(msg: domain.serviceability.GetServiceability):
    return msg.execute()
