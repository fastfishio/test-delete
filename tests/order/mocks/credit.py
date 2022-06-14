from decimal import Decimal

from libexternal.credit import model


class MockCredit:

    @staticmethod
    def get_balance(request: model.GetBalanceRequest) -> model.GetBalanceResponse:
        return model.GetBalanceResponse(
            balance=Decimal(10)
        )

    @staticmethod
    def make_transaction(request: model.MakeTransactionRequest) -> model.MakeTransactionResponse:
        return model.MakeTransactionResponse(
            status='ok',
            balance=Decimal(10),
            ref_balance=request.value
        )


class NegativeMockCredit:

    @staticmethod
    def get_balance(request: model.GetBalanceRequest) -> model.GetBalanceResponse:
        return model.GetBalanceResponse(
            balance=Decimal(-1)
        )

    @staticmethod
    def make_transaction(request: model.MakeTransactionRequest) -> model.MakeTransactionResponse:
        return model.MakeTransactionResponse(
            status='failed',
            balance=Decimal(-30),
            ref_balance=request.value
        )
