from asyncio.log import logger
import copy
import dataclasses
import functools
import json
import os
import typing
from dataclasses import dataclass, field

from noonutil.v1 import miscutil, ctxutil
from noonutil.v2 import sqlutil

import liborder
from libaccess.domain import user as libaccess_user
from libutil.translation import set_current_language


@dataclass
class Context(ctxutil.ContextBase):
    visitor_id: str = None
    user_code: str = None
    customer_code: str = None
    address_key: str = None
    lang: str = "en"
    country_code: str = "AE"
    lat: int = None
    lng: int = None
    access_info: libaccess_user.User = None

    precommit_hooks: dict = None
    postcommit_hooks: dict = None
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
        set_current_language(kwargs.get('lang', 'en'))
        return Context(**kwargs)

    @staticmethod
    def fastapi(tar_g, **kwargs):

        return Context(
            visitor_id=tar_g.visitor_id,
            customer_code=tar_g.customer_code,
            lat=tar_g.lat,
            lng=tar_g.lng,
            country_code=tar_g.country_code,
            lang=tar_g.lang,
            user_code=tar_g.user_code,
            address_key=tar_g.address_key,
            **kwargs,
        )

    @staticmethod
    def fastapi_tx(attempts, tar_g):
        def check(func):
            @functools.wraps(func)
            def wrapper(*args, **kwargs):
                @miscutil.retry_on_exception(
                    sqlutil.is_operational_error_or_unique_violation,
                    wait_random_min=10,
                    wait_random_max=300,
                    stop_max_attempt_number=attempts,
                )
                def inner():
                    cp_args = copy.deepcopy(args) if args else {}
                    cp_kwargs = copy.deepcopy(kwargs) if kwargs else {}
                    with Context.fastapi(tar_g=tar_g):
                        return func(*cp_args, **cp_kwargs)

                return inner()

            return wrapper

        return check

    def prepush(self):
        if self.user_code:
            self.access_info = libaccess_user.UserBase(user_code=self.user_code).details()

    def postpush(self):
        pass

    def register_precommit(self, key, fn):
        self.precommit_hooks[key] = fn

    def register_postcommit(self, key, fn):
        self.postcommit_hooks[key] = fn

    def push(self):
        assert self.conn is None
        self.precommit_hooks = {}
        self.postcommit_hooks = {}
        self.prepush()
        if self.isolation_level:
            self.conn = liborder.engine.connect().execution_options(isolation_level=self.isolation_level)
        else:
            self.conn = liborder.engine.connect()
        self._transaction = self.conn.begin()
        self._transaction.__enter__()
        super().push()
        self.postpush()

    def __exit__(self, exc_type, exc_value, tb):
        self.pop(exc_type, exc_value, tb)

    def pop(self, exc_type=None, exc_value=None, tb=None):
        if exc_value is None:
            for fn in self.precommit_hooks.values():
                fn()
        self._transaction.__exit__(exc_type, exc_value, tb)
        self._transaction = None
        self.conn.close()
        self.conn = None
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
