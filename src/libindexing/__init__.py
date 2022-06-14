__all__ = ['ctx', 'Context', 'DomainException', 'models', 'domain']


class DomainException(Exception):
    def __init__(self, message, *, context=None):
        self.message = message
        self.context = context or ctx.get()
        super().__init__(message)


from libutil.engines import get_engine

engine_offer = get_engine('boilerplate_offer')
engine_order = get_engine('boilerplate_order')
engine_noon_patalog = get_engine('noon_patalog')
engine_noon_cache = get_engine('noon_mp_cache_ro')

from libindexing.context import ctx, Context
from libindexing import models, domain
from . import domain, models, importers, indexers

