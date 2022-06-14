from fastapi import APIRouter

from apporder.views import order
from apporder.views import serviceability
from apporder.views import session

api_router = APIRouter()
api_router.include_router(order.router, tags=["order"], prefix='/order')
api_router.include_router(session.router, tags=["session"], prefix='/session')
api_router.include_router(serviceability.router, tags=["serviceability"], prefix='/serviceability')
