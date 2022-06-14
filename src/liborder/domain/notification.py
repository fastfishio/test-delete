import datetime
import logging

from liborder.domain.enums import Status, CancelReason
from liborder.domain.order import GetDetails
from libexternal import customer
from libexternal.notification import Notification, NotificationList, Channel

from jsql import sql
from liborder import ctx
from liborder.domain import boilerplate_event
import json

logger = logging.getLogger(__name__)


def notification_order_update(event):

    # Issues:
    # 1) some notifications might be skipped as we only consider the last order status


    if (datetime.datetime.utcnow() - event['schedule_at']).seconds // 60 > 30:
        # Skip notifications that pile up in boilerplate_event table and fail to be processed
        # One way this happens is when mp-notification-api changes and notification events fail to be processed
        logger.warning(f'notification.send:: skipping event: {event}')
        return

    event_info = event['data'].get('info', None)
    order_nr = event['data']['order_nr']
    order_details = GetDetails(order_nr=order_nr).execute(internal=True)
    eta = divmod((order_details['estimated_delivery_at'] - datetime.datetime.utcnow()).seconds, 60)[0] + 1

    customer_details = customer.get_customer_address(order_details['address_key'], fieldset='email')
    customer_code = {'recipient': customer_details.customer_code}
    email = {'recipient': customer_details.email}

    push_link = f'noon://now.noon.com/en-ae/account/orders/{order_nr}'

    notifications = []

    # notification types are per this file
    # https://docs.google.com/spreadsheets/d/1-6N6A18htgFJOodvzh-mvQ1b39zZC-TZ2KgMo70TSdw/edit#gid=0

    if event_info == 'partial_shipment':
        cancelled_items = [item for item in order_details.items if item.status_code == 'cancelled']
        notifications.extend([
            Notification(
                template_name='order_partial',
                channel_code=Channel.PUSH.value,
                to=customer_code,
                payload={
                    'order_nr': order_nr,
                    'cancel_reason': 'out of stock',
                    'deeplink': push_link
                }),
            Notification(
                template_name='order_partial',
                channel_code=Channel.EMAIL.value,
                to=email,
                payload={
                    'order_nr': order_nr,
                    'cancelled_items': cancelled_items
                })
        ])
    elif order_details.status_code == Status.CONFIRMED.value:
        notifications.extend([
            Notification(
                template_name='order_confirmed',
                channel_code=Channel.PUSH.value,
                to=customer_code,
                payload={
                    'order_nr': order_nr,
                    'eta': eta,
                    'deeplink': push_link,
                }),
        ])
    elif order_details.status_code == Status.DELIVERED.value:
        notifications.extend([
            Notification(
                template_name='order_delivered',
                channel_code=Channel.PUSH.value,
                to=customer_code,
                payload={
                    'order_nr': order_nr,
                    'deeplink': push_link
                }),
            Notification(
                template_name='order_delivered',
                channel_code=Channel.EMAIL.value,
                to=email,
                payload={
                    'order_nr': order_nr,
                })
        ])
    elif order_details.status_code == Status.UNDELIVERED.value:
        notifications.extend([
            Notification(
                template_name='order_undelivered',
                channel_code=Channel.PUSH.value,
                to=customer_code,
                payload={
                    'order_nr': order_nr,
                    'deeplink': push_link
                }),
            Notification(
                template_name='order_undelivered',
                channel_code=Channel.EMAIL.value,
                to=email,
                payload={
                    'order_nr': order_nr,
                }),
        ])
    elif order_details.status_code == Status.FAILED.value:

        fail_reason = 'unforeseen circumstances'

        if order_details['status_code_payment'] == Status.FAILED.value:
            fail_reason = 'payment failed'

        notifications.extend([
            Notification(
                template_name='order_failed',
                channel_code=Channel.PUSH.value,
                to=customer_code,
                payload={
                    'order_nr': order_nr,
                    'fail_reason': fail_reason,
                    'deeplink': push_link
                }),
        ])
    elif order_details.status_code == Status.CANCELLED.value:

        cancel_reason = 'all items are out of stock'

        # what is a better way to get cancel reason?
        # I couldn't find order-level cancel reason
        if all([item.cancel_reason_code == CancelReason.CUSTOMER_CANCELATION.value for item in order_details.items]):
            cancel_reason = 'customer cancellation'
        # if all([item.cancel_reason_code == CancelReason.OUT_OF_STOCK.value for item in order_details.items]):
        #     cancel_reason = 'all items are out of stock'

        notifications.append(Notification(
            template_name='order_cancelled',
            channel_code=Channel.PUSH.value,
            to=customer_code,
            payload={
                'order_nr': order_nr,
                'cancel_reason': cancel_reason,
                'deeplink': push_link
            }),
        )

        if cancel_reason == 'customer cancellation':
            notifications.append(Notification(
                template_name='order_cancelled',
                channel_code=Channel.EMAIL.value,
                to=email,
                payload={
                    'order_nr': order_nr,
                    'cancel_reason': cancel_reason,
                }),
            )
    elif order_details.status_code == Status.PICKED_UP.value:

        # Requirement: if some items were out of stock, don't send the OFD notification before 30 seconds
        # I couldn't think of a nicer way to do it
        # We check if the order was partial and schedule the OFD notification event accordingly

        schedule_at = sql(ctx.conn, '''
            SELECT schedule_at
            FROM boilerplate_event
            WHERE action_code = :action_code
            AND data = CAST(:data AS JSON)
            LIMIT :limit
        ''', action_code=boilerplate_event.ActionCode.NOTIFICATION_ORDER_UPDATE.name, limit=1,
                          data=json.dumps({'order_nr': order_nr, 'info': 'partial_shipment'})).scalar()

        event_time = schedule_at + datetime.timedelta(seconds=30) if schedule_at else None
        if event_time and event_time >= datetime.datetime.utcnow() and not ctx.is_testing:
            boilerplate_event.create_event(boilerplate_event.ActionCode.NOTIFICATION_ORDER_UPDATE, {'order_nr': order_nr},
                                       schedule_at=event_time)
        else:
            notifications.append(Notification(
                template_name='order_picked_up',
                channel_code=Channel.PUSH.value,
                to=customer_code,
                payload={
                    'order_nr': order_nr,
                    'eta': eta,
                    'deeplink': push_link
                })
            )

    if not notifications:
        logger.warning(f'notification.send:: empty notifications, event: {event}')
    else:
        request = NotificationList(notifications=notifications)
        response = request.send()
        logger.info(f'notification.send:: request: {request.dict()}, response: {response}')

