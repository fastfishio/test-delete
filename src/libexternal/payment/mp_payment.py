import logging

from noonhelpers.v1 import auth_team

from libexternal.payment.model import CreatePaymentIntentRequest, PaymentStatusResponse, GetTransactionStatusRequest, \
    CapturePaymentRequest, ReversePaymentRequest, RefundPaymentRequest
from liborder.domain import payment
from libutil import util

MP_PAYMENT_URL = auth_team.get_service_url('st', 'mp-payment-api-private')

logger = logging.getLogger(__name__)


class Payment:

    @staticmethod
    @util.log_call('mp_payment_get_transaction_status')
    def get_transaction_status(request: GetTransactionStatusRequest) -> PaymentStatusResponse:
        response = util.auth_post(f'{MP_PAYMENT_URL}/paymentintent/status', data=request.json(), timeout=3)
        return PaymentStatusResponse(**response.json())

    @staticmethod
    @util.log_call('mp_payment_create_payment_intent')
    def create_payment_intent(request: CreatePaymentIntentRequest) -> str:
        client_secret = auth_team.auth_post(f'{MP_PAYMENT_URL}/paymentintent/create', data=request.json()).json()
        return client_secret

    @staticmethod
    @util.log_call('mp_payment_capture')
    def capture(request: CapturePaymentRequest) -> PaymentStatusResponse:
        response = auth_team.auth_post(f'{MP_PAYMENT_URL}/payment/capture', data=request.json())
        return PaymentStatusResponse(**response.json())

    @staticmethod
    @util.log_call('mp_payment_reverse')
    def reverse(request: ReversePaymentRequest) -> PaymentStatusResponse:
        with payment.ignore_http_permanent_payment_error():
            response = auth_team.auth_post(f'{MP_PAYMENT_URL}/payment/reverse', data=request.json())
            return PaymentStatusResponse(**response.json())

    @staticmethod
    @util.log_call('mp_payment_refund')
    def refund(request: RefundPaymentRequest) -> PaymentStatusResponse:
        response = auth_team.auth_post(f'{MP_PAYMENT_URL}/payment/refund', data=request.json())
        return PaymentStatusResponse(**response.json())
