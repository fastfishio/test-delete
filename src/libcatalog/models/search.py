from typing import Any
from typing import List, Dict
from fastapi import Query
from humps import camelize
from pydantic import Field
from pydantic import validator

from libutil import util


class CatalogBaseModel(util.NoonBaseModel):
    class Config:
        validate_assignment = True
        alias_generator = camelize


class SearchSort(CatalogBaseModel):
    by: str
    dir: str


class SearchQuery(CatalogBaseModel):
    q: str | None = Query(None, min_length=1, max_length=50)
    sort: SearchSort | None
    f: Dict[str, List[str]] = {}
    page: int | None = 1
    rows: int | None = 21

    @validator("f", pre=True)
    def validate_f(cls, v):
        new_val = {}
        if not v:
            return new_val
        for attr, val in v.items():
            if not isinstance(val, (list, tuple)):
                val = [val]
            val = [each for each in val if each]
            if val:
                new_val[attr] = val
        return new_val

    @staticmethod
    def get_from_query_params(query_params=None):
        if query_params:
            return SearchQuery(**query_params.nested_dict())
        return SearchQuery()


class PLPResponse(util.NoonBaseModel):
    facets: dict | None
    results: List[Any]


class Facet(util.NoonBaseModel):
    code: str
    name: str
    type_: str = Field(..., alias="type")
    data: Any = []


class SearchResponse(util.NoonBaseModel):
    nbHits: int
    nbPages: int
    search: SearchQuery
    type: str
    facets: List[Facet]
    navPills: List[Any]
    # results would be similar to homepage
    # for now it would contain only productList, but can extend it to banner, carousel etc
    results: List[Any]
    # hits is not used, this is added as a request from FE to keep structure same as noon etc
    hits: List[Any] = []


class ProductCarouselResponse(util.NoonBaseModel):
    hits: List[Any] = []
