from libaccess import engine
from jsql import sql
from libaccess.domain.enums import Permission, ResourceType, RoleType
from libaccess import models
from libutil import util
from typing import Any, Dict, List, Tuple
import json
import logging
from libaccess.models import util as access_util

logger = logging.getLogger(__name__)


class ResourceRole(access_util.LibAccessBaseModel):
    resource_type: ResourceType
    role_type: RoleType
    permissions: List[Permission] = []
    name: str = ''
    role_desc: str = ''


def matches(row: Dict[str, Any], resource_role: ResourceRole):
    return row['resource_type'] == resource_role.resource_type and row['role_type'] == resource_role.role_type


PLATFORM_ADMIN = ResourceRole(resource_type=ResourceType.PLATFORM, role_type=RoleType.ADMIN)


class ResourceRoleBase(access_util.LibAccessBaseModel):
    resource_type: ResourceType
    role_type: RoleType

    def details(self):
        id_role = models.util.get_resource_role_id_by_code(self.resource_type, self.role_type)
        return Many(id_list=[id_role]).execute()[0]


class Many(util.NoonBaseModel):
    id_list: List[int] = []
    resource_role_tuple_list: List[Tuple[str, str]] = []

    def execute(self):
        if not self.id_list and not self.resource_role_tuple_list:
            return []
        roles = sql(
            engine,
            '''
            SELECT resource_type, role_type, permissions, name, role_desc
            FROM resource_role
            WHERE TRUE 
            {% if id_list %} AND id_resource_role IN :id_list {% endif %}
            {% if resource_role_tuple_list %} AND (resource_type, role_type) IN :resource_role_tuple_list {% endif %}
        ''',
            **self,
        ).dicts()
        for r in roles:
            json_permissions = r['permissions']
            r['permissions'] = [Permission[p] for p in json.loads(json_permissions)] if json_permissions else []
        return [ResourceRole(**r) for r in roles]
