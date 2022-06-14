import logging
from typing import List
from noonutil.v1 import miscutil
from libaccess import domain
from libaccess.domain.enums import Permission, ResourceType, RoleType
import functools

logger = logging.getLogger(__name__)

RESOURCE_PROCESSORS = dict()


def throw_error(ctx, permission: Permission, resource_type: ResourceType, resource_refs):
    assert (
        False
    ), f'Permission denied: user {ctx.access_info.get("user_code", "?")} does not have permission {permission.name} on {resource_type.name} resource "{resource_refs}"'


def assert_access(ctx, resource_type: ResourceType, resource_ref, permission: Permission):
    if not ctx.access_info:
        logger.exception(f"access_info is null!\nuser code: {ctx.user_code}")
        assert False, f'Permission denied: user does not have permission {permission.name}'
    assert resource_type in RESOURCE_PROCESSORS, f'no processor defined for resource type: {resource_type}'
    if not RESOURCE_PROCESSORS[resource_type](ctx, resource_ref, permission):
        throw_error(ctx, permission, resource_type, [resource_ref])


def get_resource_roles(ctx, resource_type: ResourceType, resource_ref) -> List[RoleType]:
    if not ctx.access_info:
        return []

    return [
        r.role_type
        for r in ctx.access_info.resources
        if r.resource_type == resource_type and r.resource_ref == resource_ref
    ]


@miscutil.cached(ttl=60)
def get_resource_role_permissions(resource_type: ResourceType, role_type: RoleType):
    return domain.resource_role.ResourceRoleBase(resource_type=resource_type, role_type=role_type).details().permissions


def has_resource_permission(ctx, resource_type: ResourceType, resource_ref, permission: Permission):
    return any(
        permission in get_resource_role_permissions(resource_type, role_type)
        for role_type in get_resource_roles(ctx, resource_type, resource_ref)
    )


def _register_processor(resource_type: ResourceType):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(ctx, *args, **kwargs):
            return func(ctx, *args, **kwargs)

        assert (
            resource_type not in RESOURCE_PROCESSORS
        ), f'duplicate processors for resource type {resource_type} defined'
        RESOURCE_PROCESSORS[resource_type] = wrapper
        return wrapper

    return decorator


@_register_processor(ResourceType.CUSTOMER_SERVICE)
def has_customer_service_permission(ctx, cs_ref, permission: Permission):
    return has_resource_permission(ctx, ResourceType.CUSTOMER_SERVICE, cs_ref, permission)
