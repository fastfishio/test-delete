import logging
import os
from decimal import Decimal

import requests
from jsql import sql

import libexternal
from libexternal.payment.model import CreatePaymentIntentRequest, GetTransactionStatusRequest, CapturePaymentRequest, \
    ReversePaymentRequest, RefundPaymentRequest
from liborder import Context
from liborder.context import ctx
from liborder.domain import status, order
from liborder.domain import credit
from liborder.domain.enums import Status, PaymentMethod, OrderPayer, PREPAID_PAYMENT_METHOD_CODES
from liborder.domain.order import GetDetails, modify_order
from libutil import util

logger = logging.getLogger(__name__)

MP_CODE = os.getenv('MP_CODE')
REF_TYPE = 'ORDER'

# todo: use a def here
ignore_http_permanent_payment_error = lambda: util.ignore_http_error(
    '.*(capture from invalid status MARKED_FOR_REVIEW|Reversal from invalid status MARKED_FOR_REVIEW|Reversal from invalid status EXPIRED|capture from invalid status EXPIRED|failed with permanent error|Reversal from invalid status FAILED|Reversal from invalid status LOCKED).*')

# TODO: Check if translations are used anywhere. If yes, translate everything. If not, remove it completely
PAYMENT_METHOD_MAP = {
    'apple_pay': {'en': 'Apple Pay', 'ar': 'Apple Pay'},
    'noonpay_wallet': {'en': 'Noon Pay Wallet', 'ar': 'Noon Pay Wallet'},
    'cc_noonpay': {'en': 'Credit Card', 'ar': 'بطاقة الائتمان'},
    'cod': {'en': 'Cash On Delivery', 'ar': 'الدفع نقداً عند الاستلام'},
    'nopayment': {'en': 'Store Credits', 'ar': 'رصيد المتجر'},
}


def get_payment_subscription_id(address_key, payment_token):
    return sql(ctx.conn, '''
        SELECT subscription_id
        FROM customer_payment_subscription
        WHERE address_key = :address_key
        AND payment_token = :payment_token
    ''', address_key=address_key, payment_token=payment_token).scalar()


def is_cvv_required(session):
    # temp hack till payments team resolves subscription issue
    # if session['payment_method_code'] != PaymentMethod.COD.value:
    #     return True
    if session.get('payment_token') and session.get('address_key'):
        subscription_id = get_payment_subscription_id(session['address_key'], session['payment_token'])
        if subscription_id:
            return False
    return True


def set_payment_intent_token(order_nr, token):
    sql(ctx.conn, '''
        UPDATE sales_order
        SET payment_intent_token = :token
        WHERE order_nr = :order_nr
    ''', order_nr=order_nr, token=token)


def delete_subscription_id(order_nr):
    order_info = sql(ctx.conn, '''
        SELECT address_key, payment_token
        FROM sales_order
        WHERE order_nr = :order_nr
    ''', order_nr=order_nr).dict()
    sql(ctx.conn, '''
        DELETE FROM customer_payment_subscription
        WHERE address_key = :address_key AND payment_token = :payment_token
    ''', **order_info)


def payment_order_create(event):
    order_nr = event['data']['order_nr']
    logger.warning('trying to create payment intent: %s', order_nr)
    order_info = order.GetDetails(order_nr=order_nr).execute(internal=True)
    logger.info(f"order_info - {order_nr}: {order_info}")
    if not order_info:
        logger.error(f"[payment_order_create] no order found: {order_nr}")
        return
    if order_info['order_collect_from_customer'] == 0:
        logger.info(f"[payment_order_create] order_collect_from_customer = 0 for {order_nr}")
        return
    if order_info['status_code_payment'] != Status.PENDING.value:
        logger.info(
            f"[payment_order_create] received {order_info['status_code_payment']} payment status for {order_nr}")
        return
    if order_info['order_credit_amount']:
        logger.info(f"capturing credit: {order_info['order_credit_amount']}")
        success = credit.capture_credit_amount(order_nr)
        if not success:
            status.PaymentStatus(order_nr, ctx={'reason': 'credit negative balance', 'wallet_issue': True}).transition(
                Status.FAILED.value)
            return
    if order_info['payment_method_code'] in PREPAID_PAYMENT_METHOD_CODES:
        address_code, address_version = order_info['address_key'].split("-")
        request = CreatePaymentIntentRequest(
            mp_code=MP_CODE,
            ref_type=REF_TYPE,
            external_ref=order_info['order_nr'],
            amount=Decimal(order_info['order_payment_amount']),
            currency_code=order_info['currency_code'],
            customer_code=order_info['customer_code'],
            address_code=address_code,
            address_version=address_version,
            create_subscription=True,
            subscription_id=order_info['subscription_id'],
        )
        payment_intent_token = libexternal.Payment.create_payment_intent(request=request)
        set_payment_intent_token(order_nr, payment_intent_token)
    else:
        logger.info(f"in payment_order_create - marking payment as done for {order_nr}")
        status.PaymentStatus(order_nr).transition(Status.DONE.value)


def payment_capture(order_nr, amount):
    assert amount >= 0, f'invalid amount: {amount}'
    logger.info(f"payment capture attempt for {order_nr}, amount: {amount}")
    order_info = sql(ctx.conn, '''
        SELECT order_payment_captured, order_payment_authorized, order_payment_refunded
        FROM sales_order
        WHERE order_nr = :order_nr
    ''', order_nr=order_nr).dict()
    assert amount <= order_info['order_payment_captured'] + order_info[
        'order_payment_authorized'], 'amount cannot be greater than authorized + captured'
    if amount == 0:
        logger.info(f"reversing payment for {order_nr}")
        request = ReversePaymentRequest(
            ref_type=REF_TYPE,
            external_ref=order_nr,
            mp_code=MP_CODE
        )
        libexternal.Payment.reverse(request=request)
    else:
        request = CapturePaymentRequest(
            amount=Decimal(amount),
            ref_type=REF_TYPE,
            external_ref=order_nr,
            mp_code=MP_CODE
        )
        libexternal.Payment.capture(request=request)
    update_payment_info(order_nr)


def payment_refund(order_nr, amount):
    assert amount >= 0, f'invalid amount: {amount}'
    logger.info(f"payment refund attempt for {order_nr}, amount: {amount}")
    order_info = sql(ctx.conn, '''
            SELECT order_payment_captured, order_payment_authorized, order_payment_refunded
            FROM sales_order
            WHERE order_nr = :order_nr
        ''', order_nr=order_nr).dict()
    if amount > order_info['order_payment_captured'] or amount < - order_info['order_payment_refunded']:
        logger.warning(f"cannot refund more than captured or less than what is already refunded: {order_nr}")
    else:
        request = RefundPaymentRequest(
            total_to_be_refunded_amount=Decimal(amount),
            ref_type=REF_TYPE,
            external_ref=order_nr,
            mp_code='MP_CODE'
        )
        libexternal.Payment.refund(request=request)
    update_payment_info(order_nr)


def update_payment_info(order_nr):
    order_info = order.GetDetails(order_nr=order_nr).execute(internal=True)
    if order_info['payment_method_code'] not in PREPAID_PAYMENT_METHOD_CODES:
        return  # this may be more appropriate to return exception
    if not order_info['payment_intent_token']:
        return  # payment event hasn't been processed yet, there is no intent token
    request = GetTransactionStatusRequest(client_secret=order_info['payment_intent_token'])
    payment_details = libexternal.Payment.get_transaction_status(request=request)

    if payment_details:
        logger.info(f"payment_details for {order_nr} -- {payment_details}")
        to_update = {
            'order_payment_authorized': payment_details.authorized_amount - payment_details.reversed_amount - payment_details.captured_amount,
            'order_payment_captured': payment_details.captured_amount,
            'order_payment_refunded': - payment_details.refunded_amount,
            # todo: see if we really need prepaid_payment_info details to be stored in order table
            'prepaid_payment_info': payment_details.json(),
            # todo: see if we really need this to be stored in order table
            'is_credit_card_used': payment_details.is_cc_payment
        }
        if payment_details.subscription_id:
            to_update['subscription_id'] = payment_details.subscription_id
        modify_order(order_nr, to_update, internal=True)
        return payment_details.status
    else:
        return  # this may be more appropriate to return exception


def refresh_payment_info_if_pending(order_nr):
    if Context.is_testing:
        return

    assert ctx.customer_code, "Customer not logged in"

    order_info = sql(ctx.conn, '''
        SELECT status_code_payment, payment_method_code 
        FROM sales_order 
        WHERE order_nr = :order_nr
        AND customer_code = :customer_code
    ''', order_nr=order_nr, customer_code=ctx.customer_code).dict()
    payment_method_code = order_info['payment_method_code']
    if order_info[
        'status_code_payment'] == Status.PENDING.value and payment_method_code in PREPAID_PAYMENT_METHOD_CODES:
        try:
            logger.info(f"payment status was pending, hence refreshing - {order_nr}")
            payment_updated(order_nr)
        except requests.exceptions.RequestException as ex:
            # ignore HTTP exceptions when doing refresh here
            logger.exception(f'exception while refreshing payment info for {order_nr}: {ex}')


def payment_updated(order_nr):
    payment_status = update_payment_info(order_nr)
    order = sql(ctx.conn, '''
        SELECT status_code_payment, order_payment_authorized, 
               order_payment_captured, order_payment_amount,
               order_credit_amount, payment_intent_token, 
               order_credit_captured
        FROM sales_order
        WHERE order_nr = :order_nr
    ''', order_nr=order_nr).dict()
    logger.info(f"[payment_updated] payment_status for {order_nr}: {payment_status}")
    status_code_payment = order['status_code_payment']
    if status_code_payment != Status.PENDING.value:
        return
    if payment_status in {'payment_failed'} and status_code_payment != Status.FAILED.value:
        logger.info(f"[payment_updated] marking the payment as failed for: {order_nr}")
        status.PaymentStatus(order_nr).transition(Status.FAILED.value)
        return
    logger.info(f"[payment_updated] payment status for {order_nr}: {status_code_payment}")
    authorized_plus_captured = order['order_payment_authorized'] + order['order_payment_captured']
    order_payment_amount = order['order_payment_amount']
    if order_payment_amount > 0 and authorized_plus_captured >= order['order_payment_amount']:
        status.PaymentStatus(order_nr).transition(Status.DONE.value)


"""
Here, if the payment is prepaid, we need to capture the order_payment_amount
"""


def capture_payment_amount(event):
    order_nr = event['data']['order_nr']
    order = GetDetails(order_nr=order_nr).execute(internal=True)
    if order.payment_method_code not in PREPAID_PAYMENT_METHOD_CODES:
        return
    order_payment_amount = order.order_payment_amount
    if order_payment_amount == 0:
        logger.warning(f"order_payment_amount is 0 for {order_nr}. Skipping capture")
        return
    # todo: verify/confirm this condition, since you can only capture once
    if order.order_payment_authorized >= order_payment_amount >= order.order_payment_captured:
        payment_capture(order_nr, order_payment_amount)
        payment_updated(order_nr)


def settle_payment(order_nr):
    # updating payment info just in case something has changed before we attempt to settle payment
    #  (one scenario it can happen is in case request from mp-payment to PG times out, but is processed on PG's side)
    _ = update_payment_info(order_nr)
    order_info = GetDetails(order_nr=order_nr).execute(internal=True)
    to_collect = order_info['order_collect_from_customer']
    collected = order_info['order_collected_from_customer']
    if util.equal_decimals(to_collect, collected):
        logger.info(f"Payment already settled for: {order_nr} - to_collect: {to_collect} collected: {collected}")
        return
    if to_collect > collected:
        diff = to_collect - collected
        if order_info['order_payment_authorized'] > order_info['order_payment_captured']:
            # if permanent payment error during capture, ignore and fallback to credit capture
            #  todo: verify if mp-payment throws error (Exception) or returns error code in response json
            #   and how can we use those error codes here
            with ignore_http_permanent_payment_error():
                return payment_capture(order_nr, min(order_info['order_payment_authorized'],
                                                     order_info['order_payment_captured'] + diff))
        # todo: should we check if balance is going negative?
        return credit.capture(order_nr, order_info['order_credit_captured'] - diff)
    if to_collect < collected:
        diff = collected - to_collect
        refunded_amount = - order_info['order_payment_refunded']
        prepaid_amount = order_info['order_payment_captured'] + refunded_amount
        # todo: thoroughly review the logic from someone
        if prepaid_amount > 0:
            to_refund = min(-refunded_amount + min(prepaid_amount, diff), order_info['order_payment_captured'])
            with ignore_http_permanent_payment_error():
                payment_refund(order_nr, to_refund)
            # (todo: add a test case for the below scenario)
            # in case there is still some diff remaining, credit it to the credit, may be there is a better way to do this
            order_info = GetDetails(order_nr=order_nr).execute(internal=True)
            diff = order_info['order_collected_from_customer'] - order_info['order_collect_from_customer']

            if diff == 0:
                return

        return credit.capture(order_nr, order_info['order_credit_captured'] + diff)


def after_payment_related_update(order_nr):
    order = GetDetails(order_nr=order_nr).execute(internal=True, formatted=False)
    invoice_info = get_invoice_info(order)
    assert invoice_info['order_collect_from_customer'] >= 0, 'order_collect_from_customer cannot go negative'
    sql(ctx.conn, '''
            UPDATE sales_order
            SET 
            order_subtotal = :order_subtotal,
            order_total = :order_total,
            order_collect_from_customer = :order_collect_from_customer,
            order_payment_amount = :order_payment_amount,
            order_delivery_fee = :order_delivery_fee,
            order_collected_from_customer = order_payment_cash_collected + order_payment_captured + order_payment_refunded - order_credit_captured
            WHERE order_nr = :order_nr
    ''', order_nr=order['order_nr'], **invoice_info)


# todo: see how adjustments would work in case of order cancelations
def get_invoice_info(order: dict):
    order_delivery_fee = order["order_delivery_fee"]
    order_payer_code = order['order_payer_code']
    order_mp_adjustment = order["order_mp_adjustment"]
    order_subtotal = 0
    if order_payer_code == OrderPayer.NONE.value:
        order_delivery_fee = 0
    else:
        for item in order["items"]:
            if not item["canceled_at"]:
                order_subtotal += item["price"]
            else:
                # for now, irrespective of cancel reason code, set delivery fee to 0
                order_delivery_fee = 0

    order_collect_from_customer = 0

    if order_payer_code == OrderPayer.CUSTOMER.value:
        order_collect_from_customer = order_subtotal + order_delivery_fee + order_mp_adjustment
    order_total = order_collect_from_customer
    order_credit_amount = util.decimal_round(order['order_credit_amount'])
    order_payment_amount = max(order_collect_from_customer + order_credit_amount, 0)
    order_payment_cash_amount = 0
    if order['payment_method_code'] == PaymentMethod.COD.value:
        order_payment_cash_amount = order_payment_amount

    return {
        'order_delivery_fee': util.decimal_round(order_delivery_fee),
        'order_subtotal': util.decimal_round(order_subtotal),
        'order_total': util.decimal_round(order_total),
        'order_mp_adjustment': util.decimal_round(order_mp_adjustment),
        'order_credit_amount': util.decimal_round(order_credit_amount),
        'order_payment_amount': util.decimal_round(order_payment_amount),
        'order_collect_from_customer': util.decimal_round(order_collect_from_customer),
        'order_payment_cash_amount': util.decimal_round(order_payment_cash_amount),
    }
