import dataclasses
import functools
import json
import os
import typing
from dataclasses import dataclass, field

from noonutil.v1 import miscutil, ctxutil
from noonutil.v2 import sqlutil


@dataclass
class Context(ctxutil.ContextBase):
    visitor_id: str = None
    customer_code: str = None
    lang: str = "en"
    country_code: str = "AE"
    is_product_carousel: bool = None
    precommit_hooks: dict = None
    isolation_level: str = None
    params: dict = field(init=False, repr=False)
    conn: typing.Any = field(init=True, repr=False, default=None)

    # static
    is_production = os.getenv('ENV') not in ('dev', 'staging')
    is_staging = os.getenv('ENV') == 'staging'
    is_testing = os.getenv('TESTING') == 'pytest'
    env = 'prod' if is_production else ('staging' if is_staging else 'dev')

    @staticmethod
    def service(**kwargs):
        return Context(**kwargs)

    @staticmethod
    def fastapi(tar_g, **kwargs):
        return Context(visitor_id=tar_g.visitor_id,
                       customer_code=tar_g.customer_code,
                       country_code=tar_g.country_code,
                       is_product_carousel=tar_g.is_product_carousel,
                       **kwargs)

    @staticmethod
    def fastapi_tx(attempts=2, wait_min=10, wait_max=300, contextargs={}):
        """
        Runs a function with a context and, in case of a retriable error, it retries it.

        This is useful to wrap routes, where you could end up hitting a deadlock or a
        "lost connection to mysql" error. Wrapping your route with this function allows
        you to automatically retry those requests.

        @fastapi_tx()
        def do_something():
            return domain.do_something()

        * attempts: maximum number of retries (keep this low so as not to retry indefinitely and put more pressure on the database)
        * wait_min: minimum time to wait before retrying
        * wait_max: maximum time to wait before retrying
        """
        import copy

        def check(func):
            @functools.wraps(func)
            def wrapper(*args, **kwargs):
                if args:
                    args = copy.deepcopy(args)
                if kwargs:
                    kwargs = copy.deepcopy(kwargs)

                @miscutil.retry_on_exception(
                    sqlutil.is_operational_error_or_unique_violation,
                    wait_random_min=wait_min,
                    wait_random_max=wait_max,
                    stop_max_attempt_number=attempts,
                )
                def inner():
                    with Context.fastapi(**contextargs):
                        return func(*args, **kwargs)

                return inner()

            return wrapper

        return check

    def prepush(self):
        pass

    def postpush(self):
        pass

    def register_precommit(self, key, fn):
        self.precommit_hooks[key] = fn

    def push(self):
        self.precommit_hooks = {}
        self.prepush()
        super().push()
        self.postpush()

    def __exit__(self, exc_type, exc_value, tb):
        self.pop(exc_type, exc_value, tb)

    def pop(self, exc_type=None, exc_value=None, tb=None):
        if exc_value is None:
            for fn in self.precommit_hooks.values():
                fn()
        super().pop(exc=exc_value)

    def json_dumps(self):
        dt = dataclasses.asdict(self)
        ret = {}
        for k, v in dt.items():
            if isinstance(v, (int, str, list, bool)):
                ret[k] = v
            elif isinstance(v, set):
                ret[k] = list(v)
        return json.dumps(ret)


ctx = Context.current

if Context.is_testing:
    assert not Context.is_production
