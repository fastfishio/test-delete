__all__ = ['engine', 'ctx', 'Context', 'DomainException', 'models', 'domain']


class DomainException(Exception):
    def __init__(self, message, *, context=None):
        self.message = message
        self.context = context or ctx.get()
        super().__init__(message)


import functools
from libaccess.domain.enums import Permission
from libaccess.domain.permission import check_permission


def with_permission(permission: Permission, *args, **kwargs):
    _args, _kwargs = args, kwargs

    def check(func):
        @functools.wraps(func)
        def wrapper(self, *args, **kwargs):
            check_permission(ctx.get(), self, permission, *_args, **_kwargs)
            return func(self, *args, **kwargs)

        return wrapper

    return check


from libutil.engines import get_engine

engine = get_engine('boilerplate_order')

from liborder.context import ctx, Context
from libcs import domain
