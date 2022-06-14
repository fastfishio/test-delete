from decimal import Decimal

from libexternal.payment.model import PaymentStatusResponse, CreatePaymentIntentRequest

payment_details = PaymentStatusResponse(
    status="AUTHORIZED",
    amount=310,
    authorized_amount=310,
    captured_amount=0,
    reversed_amount=0,
    refunded_amount=0,
    payment_method_code="cc_noonpay",
    subscription_id="12324234235"
)


class MockPayment:

    @staticmethod
    def get_transaction_status(request):
        # this is just a placeholder - we only care about captured/auth/refunded amount which we mock separately
        return payment_details

    @staticmethod
    def create_payment_intent(request: CreatePaymentIntentRequest):
        return f'PIT--{request.external_ref}'

    @staticmethod
    def capture(request):
        return 'OK'

    @staticmethod
    def refund(request):
        return 'OK'

    @staticmethod
    def reverse(request):
        return 'OK'


def get_payment_mock(authorized_amount=0, captured_amount=0, refunded_amount=0, reversed_amount=0,
                     status='payment_pending'):
    class MockPaymentCustom(MockPayment):
        @staticmethod
        def get_transaction_status(request):
            response = payment_details.copy()
            response.status = status
            response.authorized_amount = Decimal(authorized_amount)
            response.captured_amount = Decimal(captured_amount)
            response.refunded_amount = Decimal(refunded_amount)
            response.reversed_amount = Decimal(reversed_amount)
            return response

    return MockPaymentCustom
