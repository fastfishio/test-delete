import logging
import os

from boltons import iterutils

from libcatalog.context import ctx
from libcatalog.domain.category import get_code_to_id_category_map, get_id_category_to_category_map
from libcatalog.domain.offer import get_active_offers
from libcatalog.models.search import SearchQuery, Facet, ProductCarouselResponse, SearchResponse
from libutil import util
from libutil.solr_util import BoilerplateSolr, Solr
from libutil.util import guess_language
from libutil.util import safe_float

SOLR_HOST = os.getenv('SOLR_HOST')

logger = logging.getLogger(__name__)

qf_fields = {
    'en': [
        'sku',
        'en_model',
        'en_title',
        'en_title_exact',
        'en_cat',
        'en_cat_exact',
        'en_brand',
        'en_kw',
        'en_fulltext_attr',
    ],
    'ar': [
        'sku',
        'ar_model',
        'ar_title',
        'ar_title_exact',
        'ar_cat',
        'ar_cat_exact',
        'ar_brand',
        'ar_kw',
        'ar_fulltext_attr',
    ],
}

qf_field_weight = {
    'sku': 60,
    'en_model': 1,
    'en_title': 30,
    'en_title_exact': 30,
    'en_cat': 30,
    'en_cat_exact': 40,
    'en_brand': 40,
    'en_kw': 10,
    'en_fulltext_attr': 20,
    'ar_title': 40,
    'ar_model': 1,
    'ar_title_exact': 50,
    'ar_cat': 30,
    'ar_cat_exact': 40,
    'ar_brand': 40,
    'ar_kw': 10,
    'ar_fulltext_attr': 20,
}

# quick filter
qf = {
    'en': " ".join([f"{field}^{qf_field_weight[field]}" for field in qf_fields['en']]),
    'ar': " ".join([f"{field}^{qf_field_weight[field]}" for field in qf_fields['ar']]),
}


class SearchReq(util.NoonBaseModel):
    sq: SearchQuery

    def get_cat_id_solr_param(self):
        id_categories = []
        for code in self.sq.f['category']:
            id_category = get_code_to_id_category_map().get(code)
            if id_category:
                id_categories.append(id_category)
        cat_id_filter = [f"cat:{id_cat}" for id_cat in id_categories]
        if cat_id_filter:
            return f'fq={" OR ".join(cat_id_filter)}'
        return None

    def get_brand_solr_param(self):
        brand_filter = [f"brand_code:{Solr.clean(brand)}" for brand in self.sq.f['brand']]
        if brand_filter:
            return f'fq={" OR ".join(brand_filter)}'
        return None

    def get_selected_categories_for_navpills(self):
        if self.sq.q:
            return None, None
        if 'category' not in self.sq.f:
            return None, None
        id_to_category_map = get_id_category_to_category_map()
        if len(self.sq.f['category']) == 1:
            id_cat = get_code_to_id_category_map().get(self.sq.f['category'][0])
            if id_cat in id_to_category_map and not id_to_category_map[id_cat].id_category_parent:
                return id_cat, None
        elif len(self.sq.f['category']) == 2:
            id_cat_0 = get_code_to_id_category_map().get(self.sq.f['category'][0])
            id_cat_1 = get_code_to_id_category_map().get(self.sq.f['category'][1])
            if id_cat_0 not in id_to_category_map or id_cat_1 not in id_to_category_map:
                return None, None
            if id_to_category_map[id_cat_0].id_category_parent == id_cat_1:
                id_cat_0, id_cat_1 = id_cat_1, id_cat_0
            if (
                id_to_category_map[id_cat_1].id_category_parent == id_cat_0
                and not id_to_category_map[id_cat_0].id_category_parent
            ):
                return id_cat_0, id_cat_1
        return None, None

    def get_quickfilters_navpills_facets(self):
        facets = []
        navpills = []
        id_to_category_map = get_id_category_to_category_map()
        id_root_cat, id_selected_child_cat = self.get_selected_categories_for_navpills()
        if not id_root_cat:
            return navpills, facets
        facets.append(
            Facet(
                code="category",
                name="Category",
                type="category",
                data=[
                    {
                        "name": id_to_category_map[cat].name(lang=ctx.lang),
                        "code": id_to_category_map[cat].code,
                        "count": 1,
                        "children": [
                            {
                                "name": id_to_category_map[child_cat].name(lang=ctx.lang),
                                "code": id_to_category_map[child_cat].code,
                                "count": 1,
                                "children": [],
                                "isSelected": (id_selected_child_cat == child_cat),
                            }
                            for child_cat in id_to_category_map
                            if cat == id_root_cat and id_to_category_map[child_cat].id_category_parent == cat
                        ],
                        "isSelected": (id_root_cat == cat),
                    }
                    for cat in id_to_category_map
                    if not id_to_category_map[cat].id_category_parent
                ],
            )
        )
        navpills.append(
            {
                'name': id_to_category_map[id_root_cat].name(lang=ctx.lang),
                'filterName': 'Category',
                'filter': 'facets',
                'isSticky': True,
                'isSingleSelection': True,
                'code': 'category',
                'isSelected': True,
            }
        )
        for cat in id_to_category_map:
            if id_to_category_map[cat].id_category_parent != id_root_cat:
                continue
            navpills.append(
                {
                    'name': id_to_category_map[cat].name(lang=ctx.lang),
                    'filter': 'category',
                    'isSingleSelection': True,
                    'parentCode': id_to_category_map[id_root_cat].code,
                    'code': id_to_category_map[cat].code,
                    'isSelected': (cat == id_selected_child_cat),
                }
            )
        return navpills, facets

    async def execute(self):
        solr_query_params = []
        query = "*"
        facets = []
        navpills = []
        if self.sq.q:
            query = Solr.clean(self.sq.q)
            lang = guess_language(query)
            # add qf only when there is a search query string
            solr_query_params.append(f'qf={qf[lang]}')

        if self.sq.sort and self.sq.sort.by == "price":
            sort_dir = 'asc'
            if self.sq.sort.dir and self.sq.sort.dir == "desc":
                sort_dir = 'desc'
            solr_query_params.append(f'sort={self.sq.sort.by} {sort_dir}')

        if 'price_min' in self.sq.f or 'price_max' in self.sq.f:
            price_min, price_max = None, None
            if 'price_min' in self.sq.f:
                price_min = safe_float(self.sq.f['price_min'][0])
            if 'price_max' in self.sq.f:
                price_max = safe_float(self.sq.f['price_max'][0])
            # i am commenting the below check, noon also does not do any validation on min <= max
            # if 'price_min' in self.sq.f and 'price_max' in self.sq.f:
            #     self.sq.f['price_max'] = max(self.sq.f['price_min'], self.sq.f['price_max'])
            solr_query_params.append(
                f"fq=price:[{price_min if price_min else '*'} TO {price_max if price_max else '*'}]"
            )

        # category filters could be multiple
        #  /search?f[category]=milk&f[category]=oil

        if 'category' in self.sq.f:
            cat_id_filter = self.get_cat_id_solr_param()
            if cat_id_filter:
                solr_query_params.append(cat_id_filter)

        if 'brand' in self.sq.f:
            brand_filter = self.get_brand_solr_param()
            if brand_filter:
                solr_query_params.append(brand_filter)

        page_nr = max(self.sq.page, 1) if self.sq.page else 1
        solr_query_params.append(f'rows={self.sq.rows}')
        solr_query_params.append(f'start={(page_nr - 1) * self.sq.rows}')

        solr_core = f"offer_{ctx.country_code}".lower()
        # only get sku from the solr result
        solr_query_params.append(f"fl=sku")
        async with BoilerplateSolr(host=SOLR_HOST, collection=solr_core, port="8983") as solr_offer_core:
            res = await solr_offer_core.query(query=query, params=solr_query_params)
            nbHits = int(res['response']['numFound'])
            nbPages = max((nbHits + self.sq.rows - 1) // self.sq.rows, 1)
        if not ctx.is_product_carousel and not self.sq.q:
            quickfilters_navpills, quickfilters_facets = self.get_quickfilters_navpills_facets()
            navpills.extend(quickfilters_navpills)
            facets.extend(quickfilters_facets)

        docs = res['response']['docs']

        sku_list = [offer['sku'] for offer in docs]
        offers = get_active_offers(sku_list, page_nr, self.sq.rows)

        if len(offers) < len(sku_list):
            offers_sku = {o.sku for o in offers}
            missing_skus = set(sku_list) - offers_sku
            logger.warning(f"the following skus found on solr but not on spanner: {missing_skus}")

        # todo: set category facet based on search result
        numPerRow = 3
        results = [
            {
                "modules": [
                    {"type": "boilerplateProductBox", "numPerRow": numPerRow, "products": row}
                    for row in iterutils.chunked(offers, numPerRow)
                ]
            }
        ]
        if ctx.is_product_carousel:
            return ProductCarouselResponse(hits=offers)
        else:
            return SearchResponse(
                nbHits=nbHits,
                nbPages=nbPages,
                search=self.sq,
                facets=facets,
                navPills=navpills,
                results=results,
                type="catalog",
            )
