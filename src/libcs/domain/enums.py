from enum import Enum


class ActionType(Enum):
    payment_adjustment = "payment_adjustment"
    credits_issued = "credits_issued"
    cs_order_cancelation = "cs_order_cancelation"


class AdjustmentType(Enum):
    item = 'item'
    order = 'order'
