from datetime import datetime
from typing import List, Optional

from libcs.domain.enums import ActionType, AdjustmentType
from libutil import util


class CSEstimate(util.NoonBaseModel):
    event: str
    time_estimated: Optional[datetime]
    time_actual: Optional[datetime]
    status: str


class CSEvent(util.NoonBaseModel):
    event: str
    time: datetime


class CSDataPoint(util.NoonBaseModel):
    title: str
    value: str


class CSUser(util.NoonBaseModel):
    user_code: str


class CSOrderItem(util.NoonBaseModel):
    image_key: str
    status: str
    brand: Optional[str]
    title: str
    price: str
    discounted_price: Optional[str]
    sku: str
    item_nr: str
    adjustment_amount: str
    details: List[CSDataPoint] = []


class CSComment(util.NoonBaseModel):
    time: datetime
    user: str
    comment: str
    comment_code: str


class CSAdjustment(util.NoonBaseModel):
    reason_code: str
    user_code: str
    item_nr: Optional[str]
    comment: Optional[str]
    amount: str


class Location(util.NoonBaseModel):
    lat: int
    lng: int


class CSAdjustmentReason(util.NoonBaseModel):
    reason_code: str
    title: str
    adjustment_payer_code: str
    adjustment_type: AdjustmentType


class CancelReason(util.NoonBaseModel):
    code: str
    reason: str


class CSOrderSummaryEntry(util.NoonBaseModel):
    title: str
    title_style: Optional[str]
    value: str
    value_style: Optional[str]


class CSOrderSummarySection(util.NoonBaseModel):
    entries: List[CSOrderSummaryEntry]


class Action(util.NoonBaseModel):
    action_type: ActionType
    msg: str
    reason: Optional[str]
    user_code: str
    action_time: datetime
    item_nr: Optional[str]


class CSOrder(util.NoonBaseModel):
    order_nr: str
    order_placed: datetime
    delivery_ETA: datetime
    delivery_status: str
    delivery_history: List[CSEstimate]
    warehouse_history: List[CSEvent]
    logistics_history: List[CSEvent]
    customer_details: List[CSDataPoint]
    customer_code: str
    order_status_code: str
    order_status: str
    payment_method: str
    payment_info: List[CSDataPoint]
    warehouse_details: List[CSDataPoint]
    warehouse_location: Optional[Location]
    items: List[CSOrderItem]
    comments: List[CSComment] = []
    adjustments: List[CSAdjustment] = []
    is_cancelable: bool
    order_summary: List[CSOrderSummarySection]
    initial_order_summary: List[CSOrderSummarySection]
    action_log: List[Action]


class OrderSearchDetails(util.NoonBaseModel):
    order_nr: str
    customer_name: str
    country_code: str
    placed_at: datetime
    status: str


class SearchResult(util.NoonBaseModel):
    orders: List[OrderSearchDetails]
