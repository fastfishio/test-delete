import os

import sentry_sdk
from noonutil.v1 import logutil, logsql
from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
import logging

logutil.basic_config()
logsql.init()

try:
    assert False
    import sys
except AssertionError:
    pass


def before_send(event, hint):
    if 'exc_info' in hint:
        exc_type, exc_value, tb = hint['exc_info']
        if isinstance(exc_value, AssertionError):
            return None
    return event


logging.getLogger('sqlalchemy.engine').setLevel(logging.INFO)
logging.getLogger('sqlalchemy.engine').propagate = False

sentry_sdk.init(dsn=os.getenv('SENTRY_DSN'), environment=os.getenv('ENV'), integrations=[SqlalchemyIntegration()],
                before_send=before_send)
