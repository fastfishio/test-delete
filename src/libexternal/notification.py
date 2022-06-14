import logging
import os
from enum import Enum
import json

from noonhelpers.v1 import auth_team
from pydantic.fields import List

from libutil import util

NOTIFICATION_APP_URL = auth_team.get_service_url('mp', 'mp-notification-api')
MP_CODE = os.getenv('MP_CODE')  # make sure new MP code has been registered to `mp-notification-api` service

logger = logging.getLogger(__name__)


class Notification(util.NoonBaseModel):
    policy_name: str = 'default'
    template_name: str
    channel_code: str
    payload: dict
    to: dict
    idempotency_key: str = 'auto'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.idempotency_key = self.generate_idempotency_key()

    def generate_idempotency_key(self):
        return f"{self.template_name}-{self.channel_code}-{self.payload['order_nr']}"

    def send(self):
        NotificationList(notifications=[self]).send()


class NotificationList(util.NoonBaseModel):
    tenant_code: str = MP_CODE
    notifications: List[Notification]

    def send(self):
        return auth_team.auth_post(f'{NOTIFICATION_APP_URL}/notification/send',
                                   data=json.dumps(self.dict(), default=str)).json()


class Channel(Enum):
    PUSH = "push"
    EMAIL = "email"
    SMS = "sms"
