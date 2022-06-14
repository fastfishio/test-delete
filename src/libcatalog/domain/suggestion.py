import os
from typing import Any
from typing import List

from fastapi import Query
from humps import camelize

from libcatalog.context import ctx
from libcatalog.domain.offer import get_active_offers
from libcatalog.domain.search import qf
from libutil import util
from libutil.solr_util import BoilerplateSolr, Solr
from libutil.util import guess_language

SOLR_HOST = os.getenv('SOLR_HOST')


class CatalogBaseModel(util.NoonBaseModel):
    class Config:
        validate_assignment = True
        alias_generator = camelize


class SuggestionQuery(CatalogBaseModel):
    q: str | None = Query(None, min_length=1, max_length=50)

    @staticmethod
    def get_from_query_params(query_params=None):
        if query_params:
            return SuggestionQuery(**query_params.nested_dict())
        return SuggestionQuery()


class SuggestionResponse(util.NoonBaseModel):
    brands: List[Any] = []
    categories: List[Any] = []
    products: List[Any] = []
    suggestions: List[Any] = []
    facilities: List[Any] = []
    stores: List[Any] = []
    searchEngine: str = "solr"


async def get_suggestions(sq: SuggestionQuery):
    solr_query_params = []
    query = Solr.clean(sq.q)
    if len(query) < 3:
        return SuggestionResponse()
    lang = guess_language(query)
    solr_core = f"offer_{ctx.country_code}".lower()
    solr_query_params.append(f'qf={qf[lang]}')
    solr_query_params.append(f'rows=20')
    solr_query_params.append(f'start=0')
    solr_query_params.append(f"fl=sku")
    async with BoilerplateSolr(host=SOLR_HOST, collection=solr_core, port="8983") as solr_offer_core:
        res = await solr_offer_core.query(query=query, params=solr_query_params)
    docs = res['response']['docs']
    sku_list = [offer['sku'] for offer in docs]
    offers = get_active_offers(sku_list)
    return SuggestionResponse(products=offers)
