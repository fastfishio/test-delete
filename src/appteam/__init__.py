import os

# not doing in dev since tests fail on CI
if os.getenv('ENV') in ('staging', 'prod'):
    import google.cloud.logging

    client = google.cloud.logging.Client()
    # Retrieves a Cloud Logging handler based on the environment
    # you're running in and integrates the handler with the
    # Python logging module. By default this captures all logs
    # at INFO level and higher
    client.setup_logging()

from noonutil.v1 import logsql

logsql.init()
