import logging
import os
import sentry_sdk
from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
from libutil.cloud_logging_handler import CloudLoggingHandler
from google.cloud.logging.handlers import ContainerEngineHandler, AppEngineHandler
from google.cloud.logging_v2.handlers import setup_logging

# not doing in dev since tests fail on CI
if os.getenv('ENV') in ('staging', 'prod'):
    setup_logging(CloudLoggingHandler())
    root_logger = logging.getLogger()
    # use the GCP handler ONLY in order to prevent logs from getting written to STDERR
    root_logger.handlers = [handler
                            for handler in root_logger.handlers
                            if isinstance(handler, (CloudLoggingHandler, ContainerEngineHandler, AppEngineHandler))]
from noonutil.v1 import logsql

logsql.init()

try:
    assert False
    import sys

    sys.exit('ERROR asserts disabled, exiting')
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
