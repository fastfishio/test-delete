import logging
import os
from typing import List, Any

from libcatalog.context import ctx
from libcatalog.domain.search import SearchResponse, SearchQuery
from libcontent.domain.page_content import PageContent
from libutil.util import NoonBaseModel

logger = logging.getLogger(__name__)


class HomePageResponse(NoonBaseModel):
    results: List[Any]


async def get_custom_page(page_code):
    widgets = await PageContent(
        page_code=page_code,
        country_code=ctx.country_code,
        platform="app",
        content_type="mobile",
        lang=ctx.lang,
        user_group="normal_user"
    ).get_widgets()
    results = [{"modules": [widget]} for widget in widgets]

    return SearchResponse(results=results, nbHits=1, nbPages=1, search=SearchQuery(), facets=[], type="catalog",
                          navPills=[])
