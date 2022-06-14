import sqlalchemy as sa
from sqlalchemy import text, types
from sqlalchemy.dialects import mysql
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.schema import UniqueConstraint, Index
from sqlalchemy.types import UserDefinedType
import libcs.domain.enums
import liborder.domain.enums as order_enums
import liborder

TINYINT = mysql.TINYINT(unsigned=True)
SMALLINT = mysql.SMALLINT(unsigned=True)
MEDIUMINT = mysql.MEDIUMINT(unsigned=True)
INT = mysql.INTEGER(unsigned=True)
BIGINT = mysql.BIGINT(unsigned=True)
SINT = mysql.INTEGER(unsigned=False)
SBIGINT = mysql.BIGINT(unsigned=False)
CCY = sa.Numeric(13, 2)


def create_all():
    Base.metadata.create_all(liborder.engine)


def recreate_all():
    import os

    assert os.getenv('ENV') == 'dev', 'must be dev'
    assert liborder.engine.url.username == 'root'
    assert liborder.engine.url.password == 'root'
    Base.metadata.drop_all(liborder.engine)
    Base.metadata.create_all(liborder.engine)


Base = declarative_base()


# These columns should always be at the end of a table
class MixinColumn(sa.Column):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._creation_order = 9000


class POLYGON(UserDefinedType):
    def get_col_spec(self):
        return "POLYGON"


class BaseModel(Base):
    __abstract__ = True
    __bind_key__ = 'boilerplate'


class Model(Base):
    __abstract__ = True
    __bind_key__ = 'boilerplate'
    created_at = MixinColumn(types.TIMESTAMP, server_default=text('CURRENT_TIMESTAMP'), nullable=False)
    updated_at = MixinColumn(
        types.TIMESTAMP, server_default=text('CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP'), nullable=False
    )


class Session(Model):
    __tablename__ = 'session'
    id_session = sa.Column(BIGINT, primary_key=True)

    session_code = sa.Column(sa.String(50), nullable=False, unique=True)

    user_type = sa.Column(
        sa.Enum(order_enums.SessionOwnerType, values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        index=True,
    )
    # user_id would be customer_code if user_type is "customer", and visitor_id otherwise
    user_id = sa.Column(sa.String(50), nullable=False, index=True)
    country_code = sa.Column(sa.String(3), nullable=False)

    payment_method_code = sa.Column(sa.String(50), nullable=True)
    payment_token = sa.Column(sa.String(50), nullable=True)
    is_cvv_required = sa.Column(sa.Boolean, nullable=False, server_default='1')
    credit_card_bin = sa.Column(sa.String(10), nullable=True)
    credit_card_mask = sa.Column(sa.String(20), nullable=True)
    cc_type = sa.Column(sa.String(20), nullable=True)
    credit_amount = sa.Column(CCY, nullable=False, server_default='0')

    address_key = sa.Column(sa.String(100), nullable=True)
    customer_uphone_code = sa.Column(sa.String(50), nullable=True, index=True)

    is_active = sa.Column(sa.Boolean, nullable=True, server_default='1')

    __table_args__ = (
        UniqueConstraint(
            'user_type', 'user_id', 'country_code', 'is_active', name='uq_customer_country_active_session'
        ),
    )


class SessionItem(Model):
    __tablename__ = 'session_item'
    id_session_item = sa.Column(BIGINT, primary_key=True)
    id_session = sa.Column(BIGINT, nullable=False, index=True)

    id_partner = sa.Column(INT, nullable=False)
    sku = sa.Column(sa.String(50), nullable=False)
    price = sa.Column(CCY, nullable=False)
    qty = sa.Column(INT, nullable=False)

    __table_args__ = (UniqueConstraint('id_session', 'sku', name='uq_session_sku'),)


class SessionOrder(Model):
    __tablename__ = "session_order"

    id_session_order = sa.Column(BIGINT, primary_key=True)
    session_code = sa.Column(sa.String(50), nullable=False)
    order_nr = sa.Column(sa.String(50), nullable=False, unique=True)
    is_active = sa.Column(sa.Boolean, nullable=True, server_default='1')

    __table_args__ = (UniqueConstraint('session_code', 'is_active', name='uq_active_session_order'),)


class SalesOrder(Model):
    __tablename__ = 'sales_order'
    id_sales_order = sa.Column(BIGINT, primary_key=True)
    order_nr = sa.Column(sa.String(50), nullable=True)

    customer_code = sa.Column(sa.String(50), nullable=False, index=True)

    payment_method_code = sa.Column(sa.String(50), nullable=True)
    payment_token = sa.Column(sa.String(50), nullable=True)
    subscription_id = sa.Column(sa.String(50), nullable=True)
    payment_intent_token = sa.Column(sa.String(50), nullable=True, unique=True)
    credit_card_bin = sa.Column(sa.String(10), nullable=True)
    credit_card_mask = sa.Column(sa.String(20), nullable=True)

    address_key = sa.Column(sa.String(100), nullable=False)
    customer_uphone_code = sa.Column(sa.String(50), nullable=True, index=True)

    wh_code = sa.Column(sa.String(50), nullable=False, index=True)
    country_code = sa.Column(sa.String(3), nullable=False)

    # initials used for customer support
    initial_order_subtotal = sa.Column(CCY, nullable=False)
    initial_order_delivery_fee = sa.Column(CCY, nullable=False)
    initial_order_total = sa.Column(CCY, nullable=False)

    order_subtotal = sa.Column(CCY, nullable=False)
    order_delivery_fee = sa.Column(CCY, nullable=False)
    order_total = sa.Column(CCY, nullable=False)

    estimated_delivery_at = sa.Column(types.TIMESTAMP, nullable=True)
    original_estimated_delivery_at = sa.Column(types.DATETIME, nullable=True)

    order_credit_amount = sa.Column(CCY, nullable=False, server_default='0')
    order_payer_code = sa.Column(sa.String(50), nullable=False)
    order_credit_captured = sa.Column(CCY, nullable=False, server_default='0')
    # order_payment_amount is the amount to be collected by card or cash (so, basically excluding credit amount)
    order_payment_amount = sa.Column(CCY, nullable=False)
    order_payment_authorized = sa.Column(CCY, nullable=False, server_default='0')  # as received from Payment service
    order_payment_captured = sa.Column(CCY, nullable=False, server_default='0')  # as received from Payment service
    order_payment_refunded = sa.Column(CCY, nullable=False, server_default='0')
    order_payment_cash_collected = sa.Column(CCY, nullable=False, server_default='0')  # cash collected from customer
    order_mp_adjustment = sa.Column(CCY, nullable=False, server_default='0')  # (only?) CS can apply adjustments here
    is_credit_card_used = sa.Column(sa.Boolean, nullable=False, server_default='0')
    prepaid_payment_info = sa.Column(sa.JSON, nullable=True)
    order_issued_credit = sa.Column(CCY, nullable=False, server_default='0')
    order_issued_credit_captured = sa.Column(CCY, nullable=False, server_default='0')

    order_collect_from_customer = sa.Column(CCY, nullable=False)
    order_collected_from_customer = sa.Column(
        CCY, nullable=False, server_default='0'
    )  # order_payment_captured + order_payment_cash_collected + order_credit_captured

    # should we rename it to order_status_code, logistics_status_code etc?
    status_code_payment = sa.Column(sa.String(50), nullable=True)
    status_code_oms = sa.Column(sa.String(50), nullable=True)
    status_code_logistics = sa.Column(sa.String(50), nullable=True)
    status_code_order = sa.Column(sa.String(50), nullable=False, index=True)

    invoice_nr = sa.Column(sa.String(200), nullable=True)

    placed_at = MixinColumn(types.TIMESTAMP, server_default=text('CURRENT_TIMESTAMP'), nullable=False)
    delivered_at = MixinColumn(types.TIMESTAMP, nullable=True)

    __table_args__ = (UniqueConstraint('order_nr', name='uq_order_nr'),)
    # todo: add indexes


class SalesOrderHistoryEvent(Model):
    __tablename__ = 'sales_order_history_event'
    id_sales_order_history_event = sa.Column(BIGINT, primary_key=True)
    event_type = sa.Column(
        sa.Enum(order_enums.SalesOrderHistoryEventType, values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        index=True,
    )
    id_sales_order = sa.Column(BIGINT, nullable=False)
    time = sa.Column(sa.TIMESTAMP, nullable=False)
    value = sa.Column(sa.String(50), nullable=False)
    __table_args__ = (UniqueConstraint('id_sales_order', 'event_type', 'value', name='uq_sales_order_type_value'),)


class OrderEtaHistory(Model):
    __tablename__ = 'order_eta_history'
    id_order_eta_history = sa.Column(BIGINT, primary_key=True)
    id_sales_order = sa.Column(BIGINT, nullable=False, index=True)

    estimated_delivery_at = sa.Column(types.TIMESTAMP, nullable=True)


class SalesOrderItem(Model):
    __tablename__ = 'sales_order_item'
    id_sales_order_item = sa.Column(BIGINT, primary_key=True)
    id_sales_order = sa.Column(BIGINT, nullable=False, index=True)

    item_nr = sa.Column(sa.String(60), nullable=False, unique=True)

    id_partner = sa.Column(INT, nullable=False)
    sku = sa.Column(sa.String(50), nullable=False)
    price = sa.Column(CCY, nullable=False)
    canceled_at = sa.Column(types.TIMESTAMP, nullable=True)
    cancel_reason_code = sa.Column(sa.String(50), nullable=True)


class Warehouse(Model):
    __tablename__ = 'warehouse'
    id_warehouse = sa.Column(sa.Integer, primary_key=True)
    wh_code = sa.Column(sa.String(30), nullable=False, unique=True)

    country_code = sa.Column(sa.String(3), nullable=False)
    city_en = sa.Column(sa.String(100), nullable=False)
    city_ar = sa.Column(sa.String(100), nullable=False)
    area_name_en = sa.Column(sa.String(50), nullable=False)
    area_name_ar = sa.Column(sa.String(50), nullable=False)

    lat = sa.Column(BIGINT, nullable=False)
    lng = sa.Column(BIGINT, nullable=False)

    delivery_fee = sa.Column(CCY, nullable=False)
    min_order = sa.Column(CCY, nullable=False)

    is_active = sa.Column(TINYINT, nullable=False, index=True)

    created_at = sa.Column(types.TIMESTAMP, server_default=text('CURRENT_TIMESTAMP'), nullable=False)
    updated_at = sa.Column(
        types.TIMESTAMP, server_default=text('CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP'), nullable=False
    )


class Fleet(Model):
    __tablename__ = 'fleet'
    id_fleet = sa.Column(sa.Integer, primary_key=True)
    fleet_code = sa.Column(sa.String(30), nullable=False, unique=True)

    load_factor = sa.Column(CCY, nullable=False)
    load_level = sa.Column(sa.Integer, nullable=False)

    is_shutdown = sa.Column(TINYINT, nullable=False)
    is_online = sa.Column(TINYINT, nullable=False)

    hour_from = sa.Column(sa.Integer, nullable=False)
    hour_to = sa.Column(sa.Integer, nullable=False)

    created_at = sa.Column(types.TIMESTAMP, server_default=text('CURRENT_TIMESTAMP'), nullable=False)
    updated_at = sa.Column(
        types.TIMESTAMP, server_default=text('CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP'), nullable=False
    )


class WarehouseFleet(BaseModel):
    __tablename__ = 'warehouse_fleet'
    id_warehouse_fleet = sa.Column(sa.Integer, primary_key=True)
    wh_code = sa.Column(sa.String(100), index=True)
    fleet_code = sa.Column(sa.String(100), index=True)
    is_active = sa.Column(TINYINT, nullable=False)
    __table_args__ = (UniqueConstraint('wh_code', 'fleet_code', name='uq_warehouse_fleet'),)


class CustomerPaymentSubscription(BaseModel):
    __tablename__ = 'customer_payment_subscription'
    id_customer_payment_subscription = sa.Column(BIGINT, primary_key=True)

    address_key = sa.Column(sa.String(50), nullable=False)
    payment_token = sa.Column(sa.String(50), nullable=False)

    subscription_id = sa.Column(sa.String(50), nullable=False)

    created_at = sa.Column(types.TIMESTAMP, server_default=text('CURRENT_TIMESTAMP'), nullable=False)

    __table_args__ = (UniqueConstraint('address_key', 'payment_token', name='uq_subscription'),)


class BoilerplateEvent(BaseModel):
    __tablename__ = 'boilerplate_event'
    id_boilerplate_event = sa.Column(BIGINT, primary_key=True)

    action_code = sa.Column(sa.String(100), nullable=False, index=True)
    data = sa.Column(sa.JSON, nullable=True)
    schedule_at = sa.Column(sa.TIMESTAMP, nullable=False, server_default=text('CURRENT_TIMESTAMP'), index=True)
    is_processed = sa.Column(sa.Boolean, nullable=False, server_default='0', index=True)

    created_at = sa.Column(types.TIMESTAMP, server_default=text('CURRENT_TIMESTAMP'), nullable=False)
    updated_at = sa.Column(
        types.TIMESTAMP, server_default=text('CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP'), nullable=False
    )


class Shipment(Model):
    __tablename__ = 'shipment'
    id_shipment = sa.Column(BIGINT, primary_key=True)

    awb_nr = sa.Column(sa.String(100), nullable=False, unique=True)
    order_nr = sa.Column(sa.String(100), nullable=False, index=True)

    created_at = sa.Column(types.TIMESTAMP, server_default=text('CURRENT_TIMESTAMP'), nullable=False)
    updated_at = sa.Column(
        types.TIMESTAMP, server_default=text('CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP'), nullable=False
    )


class ShipmentItem(Model):
    __tablename__ = 'shipment_item'
    id_shipment_item = sa.Column(BIGINT, primary_key=True)

    id_shipment = sa.Column(BIGINT, nullable=False, index=True)
    item_nr = sa.Column(sa.String(100), nullable=False, index=True)

    created_at = sa.Column(types.TIMESTAMP, server_default=text('CURRENT_TIMESTAMP'), nullable=False)
    updated_at = sa.Column(
        types.TIMESTAMP, server_default=text('CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP'), nullable=False
    )


class CancelReason(Model):
    __tablename__ = 'cancel_reason'
    id_cancel_reason = sa.Column(BIGINT, primary_key=True)
    code = sa.Column(sa.String(100), nullable=False, unique=True)
    name_en = sa.Column(sa.String(200), nullable=False)
    name_ar = sa.Column(sa.String(200), nullable=False)
    is_internal = sa.Column(TINYINT, nullable=False)
    is_item_level = sa.Column(TINYINT, nullable=False)
    is_order_level = sa.Column(TINYINT, nullable=False)
    is_active = sa.Column(TINYINT, nullable=False, server_default='1')
    created_at = sa.Column(types.TIMESTAMP, server_default=text('CURRENT_TIMESTAMP'), nullable=False)
    updated_at = sa.Column(
        types.TIMESTAMP, server_default=text('CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP'), nullable=False
    )


class DeliveryPreference(Model):
    __tablename__ = 'delivery_preference'
    id_delivery_preference = sa.Column(BIGINT, primary_key=True)
    code = sa.Column(sa.String(100), nullable=False, unique=True)
    name_en = sa.Column(sa.String(200), nullable=False)
    name_ar = sa.Column(sa.String(200), nullable=False)
    is_active = sa.Column(TINYINT, nullable=False, server_default='1')
    allowed_for_cod = sa.Column(TINYINT, nullable=False)
    created_at = sa.Column(types.TIMESTAMP, server_default=text('CURRENT_TIMESTAMP'), nullable=False)
    updated_at = sa.Column(
        types.TIMESTAMP, server_default=text('CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP'), nullable=False
    )


# enabled preferences here only
class SessionDeliveryPreference(Model):
    __tablename__ = 'session_delivery_preference'
    id_session_delivery_preference = sa.Column(BIGINT, primary_key=True)
    id_delivery_preference = sa.Column(BIGINT, nullable=False)
    id_session = sa.Column(BIGINT, nullable=False)

    created_at = sa.Column(types.TIMESTAMP, server_default=text('CURRENT_TIMESTAMP'), nullable=False)
    updated_at = sa.Column(
        types.TIMESTAMP, server_default=text('CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP'), nullable=False
    )

    __table_args__ = (UniqueConstraint('id_session', 'id_delivery_preference', name='uq_session_delivery_preference'),)


class SalesOrderDeliveryPreference(Model):
    __tablename__ = 'sales_order_delivery_preference'
    id_sales_order_delivery_preference = sa.Column(BIGINT, primary_key=True)
    id_delivery_preference = sa.Column(BIGINT, nullable=False)
    id_sales_order = sa.Column(BIGINT, nullable=False)

    created_at = sa.Column(types.TIMESTAMP, server_default=text('CURRENT_TIMESTAMP'), nullable=False)
    updated_at = sa.Column(
        types.TIMESTAMP, server_default=text('CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP'), nullable=False
    )

    __table_args__ = (
        UniqueConstraint('id_sales_order', 'id_delivery_preference', name='uq_sales_order_delivery_preference'),
    )


class Status(Model):
    __tablename__ = 'status'
    id_status = sa.Column(INT, primary_key=True)
    code = sa.Column(sa.String(40), nullable=False, unique=True, index=True)
    name_en = sa.Column(sa.String(50), nullable=False, index=True)
    name_ar = sa.Column(sa.String(50), nullable=True, index=True)


class Country(Model):
    __tablename__ = 'country'

    id_country = sa.Column(SMALLINT, primary_key=True)
    country_code = sa.Column(sa.String(3), nullable=False, unique=True)
    currency_code = sa.Column(sa.String(3), nullable=False)
    time_zone = sa.Column(sa.String(10))
    created_at = sa.Column(types.TIMESTAMP, server_default=text('CURRENT_TIMESTAMP'), nullable=False)


class CSOrderComment(Model):
    __tablename__ = 'cs_order_comment'

    id_cs_order_comment = sa.Column(BIGINT, primary_key=True)
    order_nr = sa.Column(sa.String(100), nullable=False, index=True)
    comment_code = sa.Column(sa.String(100), nullable=False, unique=True)
    user_code = sa.Column(sa.String(200), nullable=False)
    comment = sa.Column(sa.String(1000), nullable=False)
    is_deleted = sa.Column(TINYINT, nullable=False, server_default="0")


class CSAdjustmentReason(Model):
    __tablename__ = 'cs_adjustment_reason'

    id_cs_adjustment_reason = sa.Column(BIGINT, primary_key=True)
    code = sa.Column(sa.String(100), nullable=False)
    title = sa.Column(sa.String(200), nullable=False)
    adjustment_payer_code = sa.Column(sa.String(100), nullable=False)
    adjustment_type = sa.Column(sa.Enum(libcs.domain.enums.AdjustmentType), nullable=False)
    is_active = sa.Column(TINYINT, nullable=False, server_default="1")


# what should be the unique constraint here?
# should we add item_nr in the uq constraint or we should let it be only on reason?
class CSOrderAdjustment(Model):
    __tablename__ = 'cs_order_adjustment'

    id_cs_order_adjustment = sa.Column(BIGINT, primary_key=True)
    order_nr = sa.Column(sa.String(100), nullable=False, index=True)
    adjustment_reason_code = sa.Column(sa.String(100), nullable=False, index=True)
    item_nr = sa.Column(sa.String(100), nullable=False, default='')
    comment = sa.Column(sa.String(1000), nullable=True)
    user_code = sa.Column(sa.String(200), nullable=False)
    amount = sa.Column(CCY, nullable=False)
    __table_args__ = (
        UniqueConstraint('order_nr', 'item_nr', name='uq_order_item'),
        UniqueConstraint('order_nr', 'adjustment_reason_code', name='uq_order_reason'),
    )


class CSOrderActionLog(Model):
    __tablename__ = 'cs_order_action_log'

    id_cs_order_action_log = sa.Column(BIGINT, primary_key=True)
    order_nr = sa.Column(sa.String(100), nullable=False, index=True)
    action_type = sa.Column(sa.Enum(libcs.domain.enums.ActionType), nullable=False)
    user_code = sa.Column(sa.String(200), nullable=False)
    item_nr = sa.Column(sa.String(100), nullable=True)
    reason = sa.Column(sa.String(200), nullable=False)
    amount = sa.Column(sa.String(100), nullable=True)
    created_at = sa.Column(types.TIMESTAMP, server_default=text('CURRENT_TIMESTAMP'), nullable=False, index=True)
    updated_at = sa.Column(
        types.TIMESTAMP, server_default=text('CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP'), nullable=False
    )
    __table_args__ = ()


class CustomerDefaultPayment(Model):
    __tablename__ = 'customer_default_payment'

    id_customer_default_payment = sa.Column(BIGINT, primary_key=True)
    customer_code = sa.Column(sa.String(100), nullable=False)
    country_code = sa.Column(sa.String(5), nullable=False)
    payment_method_code = sa.Column(sa.String(100), nullable=False)
    credit_card_mask = sa.Column(sa.String(100), nullable=True)
    payment_token = sa.Column(sa.String(100), nullable=True)
    is_active = sa.Column(TINYINT, nullable=False, server_default="1")
    created_at = sa.Column(types.TIMESTAMP, server_default=text('CURRENT_TIMESTAMP'), nullable=False)
    updated_at = sa.Column(
        types.TIMESTAMP, server_default=text('CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP'), nullable=False
    )
    __table_args__ = (UniqueConstraint('customer_code', 'country_code', name='uq_customer_country'),)
