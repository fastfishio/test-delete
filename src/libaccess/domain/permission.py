import logging
from libaccess import domain
from libaccess.domain.enums import Permission, ResourceType
from libaccess.domain import control
import functools

logger = logging.getLogger(__name__)

PERMISSION_PROCESSORS = dict()


def check_permission(ctx, self, permission: Permission, *args, **kwargs):
    assert ctx, 'must open a context to check permissions'
    assert ctx.user_code, 'must provide user code to check permissions'
    is_platform_admin = ctx.access_info.is_platform_admin if ctx.access_info else False
    if not is_platform_admin:
        assert (
            permission in domain.permission.PERMISSION_PROCESSORS
        ), f'permission {permission} does not have any assigned processors'
        for fn in domain.permission.PERMISSION_PROCESSORS[permission]:
            fn(permission, ctx, self, *args, **kwargs)


def register_processor(permission: Permission):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)

        if permission not in PERMISSION_PROCESSORS:
            PERMISSION_PROCESSORS[permission] = [wrapper]
        else:
            PERMISSION_PROCESSORS[permission].append(wrapper)
        return wrapper

    return decorator


# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #


@register_processor(Permission.CS_ORDER_SEARCH)
@register_processor(Permission.CS_ORDER_DETAILS)
@register_processor(Permission.CS_ORDER_COMMENT)
@register_processor(Permission.CS_ADJUST_PAYMENT)
@register_processor(Permission.CS_ISSUE_CREDIT)
@register_processor(Permission.CS_CANCEL_ORDER)
def _processor_cs(permission: Permission, ctx, self):
    control.assert_access(ctx, ResourceType.CUSTOMER_SERVICE, 'NOON_CS', permission)
