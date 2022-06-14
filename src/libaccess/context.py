from noonutil.v1 import miscutil, ctxutil
from noonutil.v2 import sqlutil
from dataclasses import dataclass, field
import dataclasses
import json
import typing
import libaccess
import os
import functools
import copy
from libutil import util

@dataclass
class Context(ctxutil.ContextBase):

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
    def fastapi(**kwargs):
        return Context(**kwargs)

    @staticmethod
    def fastapi_tx(attempts):
        def check(func):
            @functools.wraps(func)
            def wrapper(*args, **kwargs):
                if args: args = copy.deepcopy(args)
                if kwargs: kwargs = copy.deepcopy(kwargs)
                @miscutil.retry_on_exception(sqlutil.is_operational_error_or_unique_violation, wait_random_min=10, wait_random_max=300, stop_max_attempt_number=attempts)
                def inner():
                    with Context.fastapi():
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
        assert self.conn is None
        self.precommit_hooks = {}
        self.prepush()
        if self.isolation_level:
            self.conn = libaccess.engine.connect().execution_options(isolation_level=self.isolation_level)
        else:
            self.conn = libaccess.engine.connect()
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
        if isinstance(exc_value, AssertionError):
            raise util.DomainException(exc_value.args[0] if exc_value.args else 'error',
                                             context=self) from exc_value

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
