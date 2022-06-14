import logging
import os
from decimal import Decimal

from jsql import sql

import libexternal  # needed to import libexternal instead of from libexternal import Credit, so that it can be mocked
from libexternal.credit.model import GetBalanceRequest, MakeTransactionRequest
from liborder import ctx
from liborder.domain import order
from liborder.domain.enums import Status
from libutil import util

logger = logging.getLogger(__name__)
MP_CODE = os.getenv('MP_CODE')  # make sure new MP code has been registered to `mp-payment-api-credit` service
REF_TYPE_ORDER = MP_CODE + '_order'
REF_TYPE_GOODWILL = MP_CODE + '_goodwill'


def get_customer_balance(customer_code, currency_code):
    try:
        request = GetBalanceRequest(customer_code=customer_code, currency_code=currency_code)
        response = libexternal.Credit.get_balance(request=request)
        amount = response.balance
    except Exception as e:
        amount = Decimal('0')
        logger.exception(f"Exception while capturing customer credit amount: {e}")
    return Decimal(amount)


def capture(order_nr: str, amount: Decimal) -> Decimal:
    request = _make_transaction_payload(order_nr=order_nr, amount=amount)
    response = libexternal.Credit.make_transaction(request=request)
    logger.info(f"credit capture response for: {order_nr} - {response}")
    assert response.status == 'ok', 'failed to capture credit amount'

    logger.info(f"setting credit: {order_nr} -- {response.ref_balance}")
    order.modify_order(order_nr, {'order_credit_captured': response.ref_balance}, internal=True)
    return response.balance


def capture_credit_amount(order_nr):
    order_info = sql(ctx.conn, '''
        SELECT status_code_payment, order_credit_amount, order_payment_amount, payment_method_code
        FROM sales_order
        WHERE order_nr = :order_nr
    ''', order_nr=order_nr).dict()
    assert order_info['status_code_payment'] == Status.PENDING.value, 'invalid order status for credit capturing'
    assert order_info['order_credit_amount'], 'no credit amount to be captured'
    balance = capture(order_nr, order_info['order_credit_amount'])
    rounded_balance = util.decimal_round(balance)
    logger.info(f"[capture_credit_amount] credit rounded_balance for {order_nr}: {rounded_balance}")
    return rounded_balance > 0


# todo: see if this can be improved to accept order_nr directly
#  we pass events so that it can be tested easily, but we should find a better way

def capture_issued_credits(event: dict):
    order_nr = event['data']['order_nr']
    amount = sql(ctx.conn, '''
                SELECT order_issued_credit
                FROM sales_order
                WHERE order_nr = :order_nr
        ''', order_nr=order_nr).scalar()
    request = _make_transaction_payload(order_nr=order_nr, amount=amount, goodwill=True)
    response = libexternal.Credit.make_transaction(request=request)
    assert response.status == 'ok', 'failed to capture credit amount'
    order.modify_order(order_nr, {'order_issued_credit_captured': response.ref_balance}, internal=True)


def set_issued_credits(order_nr, amount):
    order.modify_order(order_nr, {'order_issued_credit': amount}, internal=True)


def _make_transaction_payload(order_nr: str, amount: Decimal, goodwill: bool = False) -> MakeTransactionRequest:
    order_info = sql(ctx.conn, '''
        SELECT
            customer_code,
            order_nr as order_ref,
            country.currency_code
        FROM sales_order
        LEFT JOIN country USING(country_code)
        WHERE order_nr = :order_nr
    ''', order_nr=order_nr).dict()
    if amount > 0:
        desc = f'{MP_CODE} - Credit for order number: {order_info["order_ref"]}'
    else:
        desc = f'{MP_CODE} - Withdrawn for order number: {order_info["order_ref"]}'

    if goodwill:
        ref_type = REF_TYPE_GOODWILL
    else:
        ref_type = REF_TYPE_ORDER

    payload = MakeTransactionRequest(
        ref_type=ref_type,
        ref_code=order_nr,
        currency_code=order_info['currency_code'],
        customer_code=order_info['customer_code'],
        description=desc,
        issued_by=MP_CODE,
        mp_code=MP_CODE,
        is_withdrawable=True,
        value=amount
    )
    return payload
