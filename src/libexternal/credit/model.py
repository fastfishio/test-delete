from decimal import Decimal

from pydantic import BaseModel


class GetBalanceRequest(BaseModel):
    customer_code: str
    currency_code: str


class GetBalanceResponse(BaseModel):
    balance: Decimal


class MakeTransactionRequest(BaseModel):
    ref_type: str
    ref_code: str
    description: str
    issued_by: str
    value: Decimal
    customer_code: str
    currency_code: str
    mp_code: str
    is_withdrawable: bool = False


class MakeTransactionResponse(BaseModel):
    status: str | None
    balance: Decimal | None
    ref_balance: Decimal | None
