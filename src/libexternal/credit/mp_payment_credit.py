from noonhelpers.v1 import auth_team

from libexternal.credit import model
from libutil import util

CREDIT_URL = auth_team.get_service_url('st', 'mp-payment-api-credit')


class Credit:
    @staticmethod
    @util.log_call('credit_get_balance')
    def get_balance(request: model.GetBalanceRequest) -> model.GetBalanceResponse:
        url = f'{CREDIT_URL}/credit/balance'
        response = auth_team.auth_post(url, data=request.json())
        return model.GetBalanceResponse(**response.json())

    @staticmethod
    @util.log_call('credit_make_transaction')
    def make_transaction(request: model.MakeTransactionRequest) -> model.MakeTransactionResponse:
        url = f'{CREDIT_URL}/credit/transaction/{request.ref_code}'
        response = auth_team.auth_post(url, data=request.json())
        return model.MakeTransactionResponse(**response.json())
