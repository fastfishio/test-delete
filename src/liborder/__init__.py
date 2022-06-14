__all__ = ['engine', 'ctx', 'Context', 'DomainException', 'models', 'domain']


class DomainException(Exception):
    def __init__(self, message, *, context=None):
        self.message = message
        self.context = context or ctx.get()
        super().__init__(message)


from libutil.engines import get_engine

engine = get_engine('boilerplate_order')

from liborder.context import ctx, Context
from liborder import models, domain
