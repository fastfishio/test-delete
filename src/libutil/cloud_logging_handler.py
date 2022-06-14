import json
import math
from google.cloud.logging_v2.handlers.container_engine import ContainerEngineHandler


def format_stackdriver_json(record, message):
    """Helper to format a LogRecord in Stackdriver fluentd format.
    Returns:
        str: JSON str to be written to the log file.
    """
    subsecond, second = math.modf(record.created)

    payload = {
        "message": message,
        "timestamp": {"seconds": int(second), "nanos": int(subsecond * 1e9)},
        "thread": record.thread,
        "severity": record.levelname,
    }

    path = getattr(record, 'path', None)
    method = getattr(record, 'method', None)
    time_ms = getattr(record, 'time_ms', None)
    code = getattr(record, 'code', None)

    if path and method and time_ms and code:
        payload.update({
            'path': path,
            'method': method,
            'time_ms': time_ms,
            'code': code
        })

    return json.dumps(payload, ensure_ascii=False)


class CloudLoggingHandler(ContainerEngineHandler):
    def format(self, record):
        """Format the message into JSON expected by fluentd.
        Args:
            record (logging.LogRecord): The log record.
        Returns:
            str: A JSON string formatted for GKE fluentd.
        """
        message = super(ContainerEngineHandler, self).format(record)
        return format_stackdriver_json(record, message)
