import datetime
import json
from enum import auto, Enum
from typing import List

from jsql import sql
from noonutil.v2 import sqlutil

from liborder import ctx, models


class ActionCode(Enum):
    PAYMENT_ORDER_CREATE = auto()
    PAYMENT_ORDER_CAPTURE = auto()
    SETTLE_PAYMENT = auto()
    CAPTURE_ISSUED_CREDITS = auto()

    # When a shipment is created for an order, we need to decide whether to send
    # the available shipments and cancel the remaining items, or wait for the rest
    ORDER_SHIPMENT_CREATED = auto()
    # This event will be created in two cases:
    #   1) Current shipments cover the entire order (scheduled immediately)
    #   2) If the first created shipment does not cover all orders (scheduled after 5 minutes)
    # once it triggers, we send all the available shipments to logistics and cancel the remaining items
    ORDER_READY_FOR_PICKUP = auto()
    # Cancel order after a certain amount of time if no shipments are created
    CANCEL_ORDER_WITH_NO_SHIPMENTS = auto()

    LOGISTICS_ORDER_UPDATE = auto()

    GENERATE_INVOICE = auto()

    NOTIFICATION_ORDER_UPDATE = auto()

    DEFAULT_PAYMENT_UPDATE = auto()


def create_event(action_code: ActionCode, data, schedule_at=None):
    event = {
        "action_code": action_code.name,
        "data": json.dumps(data, default=str)
    }
    if schedule_at:
        event['schedule_at'] = schedule_at
    sqlutil.insert_one(ctx.conn, models.tables.BoilerplateEvent, event)
    return event


class BoilerplateEvent:
    action_code: ActionCode
    data: dict
    schedule_at: datetime.datetime = None

    def __init__(self, action_code: ActionCode, data: dict, schedule_at=None):
        self.action_code = action_code
        self.data = data
        self.schedule_at = schedule_at


def create_events(events: List[BoilerplateEvent]):
    to_insert = []
    for event in events:
        row = {
            "action_code": event.action_code.name,
            "data": json.dumps(event.data, default=str)
        }
        if event.schedule_at:
            row['schedule_at'] = event.schedule_at
        to_insert.append(row)
    sqlutil.insert_batch(ctx.conn, models.tables.BoilerplateEvent, to_insert)


def get_events(action_code: ActionCode, num_events=3):
    events = sql(ctx.conn, '''
        SELECT *
        FROM boilerplate_event
        WHERE action_code = :action_code
        AND schedule_at <= CURRENT_TIMESTAMP()
        AND is_processed = 0 
        LIMIT :limit
    ''', action_code=action_code.name, limit=num_events).dicts()
    for event in events:
        event['data'] = json.loads(event['data'])
    return events


def delete_event(id_event):
    if not id_event:
        return
    sql(ctx.conn, '''
        UPDATE boilerplate_event
        SET is_processed = 1
        WHERE id_boilerplate_event = :id_event
    ''', id_event=id_event)
