import logging

from liborder.domain import enums
from liborder.domain import order
from liborder.domain import payment
from liborder.domain.enums import OrderPayer
from liborder.domain.boilerplate_event import ActionCode, create_events, BoilerplateEvent
from liborder.models.status import Status

logger = logging.getLogger(__name__)

ORDER_TERMINAL_STATES = {enums.Status.DELIVERED.value, enums.Status.UNDELIVERED.value, enums.Status.CANCELLED.value,
                         enums.Status.FAILED.value}
LOGISTICS_TERMINAL_STATES = {enums.Status.DELIVERED.value, enums.Status.UNDELIVERED.value, enums.Status.CANCELLED.value}


class PaymentStatus(Status):
    TABLE = 'sales_order'
    PK = 'order_nr'
    KEY = 'status_code_payment'

    def pending_to_done(self):
        pass

    def pending_to_canceled(self):
        pass

    def pending_to_failed(self):
        pass

    def after_failed(self):
        to_update = {
            'order_payer_code': OrderPayer.NONE.value,
            'status_code_order': enums.Status.FAILED.value
        }
        order.modify_order(order_nr=self.id, modifier=to_update, internal=True)
        if not self.ctx.get('wallet_issue'):
            payment.delete_subscription_id(self.id)

        # todo: insert 2 events in one query
        create_events([
            BoilerplateEvent(action_code=ActionCode.SETTLE_PAYMENT, data={'order_nr': self.id}),
            BoilerplateEvent(action_code=ActionCode.NOTIFICATION_ORDER_UPDATE, data={'order_nr': self.id})
        ])
        order.reactivate_order_session(order_nr=self.id)

    # todo: check if payment failed and canceled be combined
    def after_canceled(self):
        # todo: we are not keeping statuses for sales_order_item
        #  so it always remains 'confirmed' state, handle this scenario
        to_update = {
            'order_payer_code': OrderPayer.NONE.value,
            'status_code_order': enums.Status.FAILED.value
        }
        order.modify_order(order_nr=self.id, modifier=to_update, internal=True)

        # TODO: can we remove this? canceled shouldn't be due to wallet_issue?
        if not self.ctx.get('wallet_issue'):
            payment.delete_subscription_id(self.id)
        create_events([
            BoilerplateEvent(action_code=ActionCode.SETTLE_PAYMENT, data={'order_nr': self.id}),
        ])
        order.reactivate_order_session(order_nr=self.id)

    def after_done(self):
        # todo: we are not keeping statuses for sales_order_item
        #  so it always remains 'confirmed' state, handle this scenario

        modifier = {'status_code_order': enums.Status.CONFIRMED.value}
        order_details = order.modify_order(order_nr=self.id, modifier=modifier, trigger_payment_update=False, internal=True)
        events = [
            BoilerplateEvent(action_code=ActionCode.NOTIFICATION_ORDER_UPDATE, data={'order_nr': self.id}),
        ]
        if order_details.payment_method_code in enums.PREPAID_PAYMENT_METHOD_CODES:
            # Should we shorten the keys in data?
            events.append(BoilerplateEvent(action_code=ActionCode.DEFAULT_PAYMENT_UPDATE,
                                       data={
                                            'customer_code': order_details.customer_code,
                                            'country_code': order_details.country_code,
                                            'payment_method_code': order_details.payment_method_code,
                                            'credit_card_mask': order_details.credit_card_mask,
                                            'payment_token': order_details.payment_token
                                       }))
        create_events(events)
        order.eta_order_update(order_details)
