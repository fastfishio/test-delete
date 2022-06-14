import logging
from enum import Enum

from .translation import lazy_gettext as _

logger = logging.getLogger()


class Error(Enum):
    INVALID_PAYMENT_METHOD = 'E0001', _('invalid payment method')

    TEST_ERROR = 'E0149', 'TEST ERROR'


def error_msg(error, **kwargs):
    error_code, error_text = error.value
    msg = f'{error_code} - {error_text}'.format(**kwargs)
    return msg


def get_type(error):
    if not error:
        return None
    error_code = error.split()[0]
    if len(error_code) != 5 or error_code[0] != 'E':
        return None
    return error_code


def get_msg(error):
    if len(error) >= 8 and error[0] == 'E' and error[5:8] == ' - ':
        return error[8:]
    return error


error_codes = [error_code for error_code, _ in list(map(lambda x: x.value, Error))]
assert len(error_codes) == len(set(error_codes)), 'dup error code'
