import decimal
import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta, datetime
from decimal import Decimal
from enum import Enum
import pydantic
from humps import camelize
from noonutil.v1 import miscutil
import contextlib
import functools
import inspect

logger = logging.getLogger(__name__)


def encode_date(d=None):
    import datetime

    date = d or datetime.datetime.today()
    num_to_char = lambda n: str(n) if n < 10 else chr(ord('A') + (n - 10))
    return f'{num_to_char(date.year - 2020 + 10)}{num_to_char(date.month)}{num_to_char(date.day)}'


def get_digest(x):
    import re

    return re.sub(r'[AEIOU]', '', x, flags=re.IGNORECASE)


def get_cc_bin(cc_mask):
    try:
        return cc_mask[:6]
    except Exception as _:
        assert False, 'invalid credit card mask'


@contextlib.contextmanager
def ignore_http_error(pattern):
    from requests import HTTPError
    import re

    p = re.compile(pattern)
    try:
        yield
    except HTTPError as exc:
        if not p.search(exc.response.text):
            raise


class DomainException(Exception):
    def __init__(self, message, context):
        self.message = message
        self.context = context
        super().__init__(message)


class AutoNameEnum(Enum):
    def _generate_next_value_(name, start, count, last_values):
        return name


class NoonBaseModel(pydantic.BaseModel):
    def dump(self):
        return self.dict(by_alias=True, skip_defaults=True)

    def update(self, d):
        tuples = d.items() if hasattr(d, 'items') else d
        for k, v in tuples:
            self[k] = v

    def keys(self):
        return self.__dict__.keys()

    def get(self, *k):
        return self.__dict__.get(*k)

    def __getitem__(self, key):
        return self.__dict__[key]

    def __setitem__(self, key, val):
        self.__dict__[key] = val

    def __delitem__(self, key):
        del self.__dict__[key]

    def __iter__(self):
        return iter(self.__dict__)

    def __len__(self):
        return len(self.__dict__)

    @classmethod
    def bind(cls, func):
        setattr(cls, func.__name__, _bind_wrapper(func))
        return func

    @classmethod
    def get_classes(cls, rows):
        """
        This method will convert list[dict] into list[model_class]
        """
        if not rows:
            return []
        return [cls(**r) for r in rows]

    @classmethod
    def get_dicts(cls, rows, *args, **kwargs):
        """
        This method will convert list[dict] into list[model_class]
        """
        if not rows:
            return []
        return [r.dict(*args, **kwargs) for r in rows]

    class Config:
        use_enum_values = True
        allow_population_by_field_name = True
        alias_generator = camelize


def unbind(func, cls):
    @functools.wraps(func)
    def wrapper(**kwargs):
        instance = cls(**kwargs)
        return getattr(instance, func.__name__)()

    return wrapper


def bind(func):
    return _bind_wrapper(func)


def _bind_wrapper(func):
    spec = inspect.getfullargspec(func)

    @functools.wraps(func)
    def wrapper(self):
        real_args = []
        d = self.dict()

        for arg in spec.args:
            real_args.append(d[arg])
            del d[arg]

        if not spec.varkw:
            d = {}

        return func(*real_args, **d)

    return wrapper


def log_call(logging_topic=None):
    def wrapper(fn):
        @functools.wraps(fn)
        def wrapped(*args, **kwargs):
            topic = logging_topic or fn.__name__
            logger.info(f'{topic}, args:{args}, kwargs:{kwargs}')
            ret = fn(*args, **kwargs)
            logger.info(f'{topic}, args:{args}, kwargs:{kwargs}, response:{ret}')
            return ret

        return wrapped

    return wrapper


def auth_post(url, payload={}, data=None, *, headers={}, timeout=10, session=None, allow_error_status=None):
    from noonhelpers.v1.auth_team import get_auth_session
    import json

    session = session or get_auth_session()
    headers = {'content-type': 'application/json', **headers}
    data = data or json.dumps(payload)
    ret = session.post(url, data=data, headers=headers, timeout=timeout)
    content = ret.content
    if not (allow_error_status and ret.status_code in allow_error_status):
        ret.raise_for_status()
    return ret


LATLNGSCALE = 10000000


def latlng_from_int(value):
    return Decimal(str(int(value) / LATLNGSCALE))


def latlng_to_int(value):
    return int(Decimal(value) * LATLNGSCALE)


def parse_location_cookie(location_cookie):
    try:
        location = miscutil.decode_base64(location_cookie)
        location = json.loads(location)
        return location['lat'], location['lng']
    except Exception:
        return 0, 0


def guess_language(word):
    ARABIC_SET = {'ح', 'ص', 'إ', 'آ', 'ء', 'ة', 'خ', 'ز', 'و', 'ه', 'ت', 'ئ', 'ن', 'ي', 'ق', 'ذ', 'ج', 'ع', 'ط', 'م',
                  'ك', 'غ', 'د', 'ل', 'س', 'ا', 'ض', 'ب', 'ف', 'ث', 'ؤ', 'ظ', 'أ', 'ش', 'ر'}
    return 'ar' if set(word) & ARABIC_SET else "en"


def safe_float(i, *, default=None):
    try:
        return float(i)
    except Exception:
        return default


def canonicalize(psku):
    valid_characters = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ'
    trim_leading, trim_trailing = '0', ''
    psku = psku.upper()
    psku = ''.join([c for c in psku if c in valid_characters])
    return psku.lstrip(trim_leading).rstrip(trim_trailing)


def equal_decimals(a, b):
    return abs(Decimal(a) - Decimal(b)) <= 1e-09


def decimal_round(val, replace_zero=False):
    if val is None:
        return None
    if val <= 0.001 and replace_zero:
        return 'FREE'
    return Decimal(Decimal(val).quantize(Decimal('.01'), rounding=decimal.ROUND_HALF_UP))


def get_credit_card_type(cc_mask):
    if not cc_mask:
        return None
    cc_type_map = {'2': 'MASTERCARD', '3': 'AMEX', '4': 'VISA', '5': 'MASTERCARD', '6': 'DISCOVER'}
    return cc_type_map.get(cc_mask[0])


def from_cent(cent):
    return Decimal(str(cent / 100))


threadpool = ThreadPoolExecutor(max_workers=5)


def get_delta_from_tz(time_zone):
    regex = re.compile('(-|\+)?([0-9]+):([0-9]+)')
    match = regex.match(time_zone)
    delta = timedelta(hours=int(match.group(2)), minutes=int(match.group(3)))
    if match.group(1) and match.group(1) == '-':
        delta = -delta
    return delta


def format_date(date: datetime):
    suffix = 'th' if 11 <= date.day <= 13 else {1: 'st', 2: 'nd', 3: 'rd'}.get(date.day % 10, 'th')
    return date.strftime('{S} %b, %Y').replace('{S}', str(date.day) + suffix)


def get_msg(error):
    return error


def generate_exception_handler(
    status_code, *, sentry_level='warning', client_error_message=None, include_traceback=False, monitoring_key=False
):
    import traceback
    import sentry_sdk
    from fastapi.responses import JSONResponse
    import os

    def handler(request, exception):
        with sentry_sdk.configure_scope() as scope:
            scope.level = sentry_level
            content = {'error': client_error_message or str(exception)}
            if include_traceback and os.getenv('ENV') in ('dev', 'staging'):
                content['traceback'] = traceback.format_exception(type(exception), exception, exception.__traceback__)
            return JSONResponse(content=content, status_code=status_code)

    return handler


def is_email(email):
    regex = re.compile(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}')
    return re.fullmatch(regex, email)


def is_phone(phone):
    regex = re.compile(r'^(|\+)([0-9]{1,3})(-|)([0-9]{2,4})(-|)([0-9]{6,10})')
    return re.fullmatch(regex, phone)
