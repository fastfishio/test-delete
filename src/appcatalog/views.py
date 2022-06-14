import logging

from fastapi import APIRouter, Request

from appcatalog.web import g
from libcatalog import Context, domain, ctx
from libcatalog.domain.offer import get_pdp_offer
from libcatalog.domain.page import get_custom_page
from libcatalog.domain.search import SearchQuery
from libcatalog.domain.suggestion import SuggestionQuery
from libcatalog.domain.suggestion import get_suggestions
from libcatalog.models.payloads import PdpRequest

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get('/home', summary='get homepage content', tags=['content'])
async def homepage():
    with Context.fastapi(tar_g=g):
        return await get_custom_page(f"home_app_mobile_{ctx.country_code.lower()}")


@router.get('/page/{page_code}', summary='get homepage content', tags=['content'])
async def get_page(page_code):
    with Context.fastapi(tar_g=g):
        return await get_custom_page(page_code)


@router.get('/search', summary='search for products', tags=['product'])
async def search_get(request: Request):
    with Context.fastapi(tar_g=g):
        sq = SearchQuery.get_from_query_params(request.state.query_params)
        if sq == SearchQuery():  # if the search object is empty then return homepage response instead
            return await get_custom_page(f"home_app_mobile_{ctx.country_code.lower()}")
        else:
            return await domain.search.SearchReq(sq=sq).execute()


@router.post('/search', summary='search for products', tags=['product'])
async def search_post(msg: SearchQuery):
    with Context.fastapi(tar_g=g):
        if msg == SearchQuery():
            return await get_custom_page(f"home_app_mobile_{ctx.country_code.lower()}")
        else:
            return await domain.search.SearchReq(sq=msg).execute()


@router.post('/pdp', summary='product details', tags=['product'])
async def pdp(request: PdpRequest):
    with Context.fastapi(tar_g=g):
        return await get_pdp_offer(sku=request.sku)


@router.get('/suggestions', summary='search suggestions', tags=['product'])
async def suggestions(request: Request):
    with Context.fastapi(tar_g=g):
        sq = SuggestionQuery.get_from_query_params(request.state.query_params)
        return await get_suggestions(sq)
