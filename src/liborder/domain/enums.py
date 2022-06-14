from enum import Enum


class Status(Enum):
    PENDING = "pending"  # payment, order
    DONE = "done"  # payment
    CANCELLED = "cancelled"  # payment, hyperlocal, oms, order
    FAILED = "failed"  # payment, order
    SHIPPED = "shipped"  # oms
    NOT_SYNCED = "not_synced"  # hyperlocal, oms
    CONFIRMED = "confirmed"  # order, oms?
    READY_FOR_PICKUP = "ready_for_pickup"  # order
    PENDING_ASSIGNMENT = "pending_assignment"  # hyperlocal
    ASSIGNED = "assigned"  # hyperlocal
    ARRIVED_AT_PICKUP = "arrived_at_pickup"  # hyperlocal, order
    PICKED_UP = "picked_up"  # hyperlocal, order
    ARRIVED_AT_DELIVERY = "arrived_at_delivery"  # hyperlocal, order
    DELIVERED = "delivered"  # hyperlocal, order
    UNDELIVERED = "undelivered"  # hyperlocal, order


class CancelReason(Enum):
    OUT_OF_STOCK = "out_of_stock"
    CUSTOMER_CANCELATION = "customer_cancelation"
    CS_CANCELATION = 'cs_cancelation'


class PaymentMethod(Enum):
    CC_NOONPAY = "cc_noonpay"
    COD = "cod"
    APPLE_PAY = "apple_pay"
    NOPAYMENT = "nopayment"


class AdjustmentReasonType(Enum):
    ITEM = 'item'
    ORDER = 'order'


PREPAID_PAYMENT_METHOD_CODES = [PaymentMethod.CC_NOONPAY.value, PaymentMethod.APPLE_PAY.value]


# todo: @chandan
# here we are keeping only customer and None for now
#  later we can also keep MP (boilerplate) in case of full refunds due to delivery issues etc?
class OrderPayer(Enum):
    CUSTOMER = "customer"
    NONE = "none"


class SessionOwnerType(Enum):
    CUSTOMER = 'customer'
    GUEST = 'guest'


class SalesOrderHistoryEventType(Enum):
    ORDER_STATUS = 'order_status'
    LOGISTICS = 'logistics'
