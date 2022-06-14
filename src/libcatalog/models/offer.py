import json
import math
from typing import List, Dict

from pydantic import BaseModel
from decimal import Decimal


class OfferBase(BaseModel):
    sku: str
    id_partner: int

    title: str
    brand: str = ""
    brand_code: str = ""

    price: Decimal
    sale_price: Decimal
    discount_percent: int | None

    image_key: str | None
    image_keys: List[str] | None
    max_qty: int = 1

    def __init__(self, data: Dict):
        super().__init__(**data)
        if data.get('image_keys_json'):
            self.image_keys = json.loads(data.get('image_keys_json'))
            self.image_key = self.image_keys[0]

        if self.sale_price < self.price:
            self.discount_percent = math.floor((self.price - self.sale_price) / self.price * 100)

        self.max_qty = min(data.get('stock_customer_limit'), data.get('stock_net'))


class Offer(OfferBase):
    index: int

    def __init__(self, data: Dict, index: int):
        data['index'] = index
        super().__init__(data)


class OfferPdp(OfferBase):
    is_buyable: bool

    def __init__(self, data: Dict):
        data['is_buyable'] = data.get('stock_net') > 0
        super().__init__(data)
