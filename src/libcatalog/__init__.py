from libutil.engines import get_engine

__all__ = ['engine', 'ctx', 'Context', 'DomainException', 'models', 'domain', 'NotFoundException']


class DomainException(Exception):
    def __init__(self, message, *, context=None):
        self.message = message
        self.context = context or ctx.get()
        super().__init__(message)


class NotFoundException(Exception):
    def __init__(self, message):
        self.message = message
        super().__init__(message)


engine = get_engine('boilerplate_catalog')
engine_noon_catalog = get_engine('noon_catalog')
engine_noon_mp_cache_ro = get_engine('noon_mp_cache_ro')

from libcatalog import models, domain
from libcatalog.context import ctx, Context
