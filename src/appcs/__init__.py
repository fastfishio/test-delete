import os
import logging
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
