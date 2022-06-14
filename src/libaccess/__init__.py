from libutil.engines import get_engine

engine = get_engine('boilerplate_access')

from libaccess.context import ctx, Context
from libaccess.domain.enums import Permission, ResourceType
from libaccess.domain.control import assert_access
