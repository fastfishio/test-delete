from decimal import Decimal
from pydantic import BaseModel


class CreatePaymentIntentRequest(BaseModel):
    mp_code: str
    ref_type: str
    external_ref: str
    amount: Decimal
    currency_code: str
    customer_code: str
    address_code: str
    address_version: str
    create_subscription: bool
    subscription_id: str | None


class GetTransactionStatusRequest(BaseModel):
    client_secret: str


class CapturePaymentRequest(BaseModel):
    amount: Decimal
    ref_type: str
    external_ref: str
    mp_code: str


class RefundPaymentRequest(BaseModel):
    total_to_be_refunded_amount: Decimal
    ref_type: str
    external_ref: str
    mp_code: str
    transaction_reference: str | None


class ReversePaymentRequest(BaseModel):
    ref_type: str
    external_ref: str
    mp_code: str


class PaymentStatusResponse(BaseModel):
    status: str | None
    redirect_url: str | None
    amount: Decimal | None
    authorized_amount: Decimal | None
    captured_amount: Decimal | None
    reversed_amount: Decimal | None
    refunded_amount: Decimal | None
    payment_method_code: str | None
    subscription_id: str | None
    reference: str | None
    customer_code: str | None
    id_token: int | None
    is_cc_payment: bool = False
    message: str | None
    error_message: str | None
