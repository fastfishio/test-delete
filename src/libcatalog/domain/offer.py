from typing import List
from string import Template
from libcatalog import NotFoundException
from libcatalog.context import ctx
from libcatalog.models.offer import OfferPdp, Offer
from libutil.spanner_util import boilerplate_spanner

OFFER_QUERY_TEMPLATE = Template('''
        SELECT
            p.sku,
            o.id_partner,

            plang.title,
            plang.brand,
            p.brand_code,

            o.msrp as price,
            o.offer_price as sale_price,

            p.image_keys as image_keys_json,
            COALESCE(o.stock_customer_limit, 10) as stock_customer_limit,
            os.stock_net
        FROM product p
        JOIN $product_table plang USING (sku)
        JOIN offer o USING (sku)
        JOIN offer_stock os ON os.sku = o.sku
        WHERE p.sku IN UNNEST(@sku_list)
        AND os.stock_net > 0
    ''')


async def get_pdp_offer(sku: str) -> OfferPdp:
    query = OFFER_QUERY_TEMPLATE.substitute(product_table=f'product_{ctx.lang}')
    data = boilerplate_spanner().execute_query(query, sku_list=[sku]).dict()
    if not data:
        raise NotFoundException("Product not found")

    return OfferPdp(data)


def get_active_offers(sku_list: List[str], page: int = 1, rows: int = 20) -> List[Offer]:
    if len(sku_list) == 0:
        return []

    query = OFFER_QUERY_TEMPLATE.substitute(product_table=f'product_{ctx.lang}')
    data = boilerplate_spanner().execute_query(query, sku_list=sku_list).dicts()
    data = sorted(data, key=lambda x: sku_list.index(x["sku"]))

    idx = (page - 1) * rows + 1
    offers = []
    for o in data:
        offer = Offer(o, idx)
        idx += 1
        offers.append(offer)
    return offers
