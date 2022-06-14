from libaccess import models, engine
from libaccess.domain import resource_role
from libaccess.domain.enums import ResourceType, RoleType
from jsql import sql
from noonutil.v1 import miscutil
from noonutil.v2 import sqlutil
from libutil import util
from libaccess.models import util as access_util
from typing import List
import logging

logger = logging.getLogger(__name__)


class UserAccess(access_util.LibAccessBaseModel):
    resource_type: ResourceType
    role_type: RoleType
    resource_ref: str


class User(access_util.LibAccessBaseModel):
    user_code: str
    resources: List[UserAccess]
    is_platform_admin: bool


@miscutil.cached()
def get_or_create_user_id(user_code):
    '''dont use context connection as results are cached and might not end up committed'''
    # The above comment doesn't hold anymore after we removed user_name from db table

    assert user_code, f'invalid user code: {user_code}'

    id_user = models.util.get_user_id_by_code(user_code, allow_none=True)
    if not id_user:
        id_user = sqlutil.insert_one(engine, models.tables.User, {'code': user_code}).lastrowid

    return id_user


class UserBase(util.NoonBaseModel):
    user_code: str

    def details(self):
        user = Many(id_user_list=[get_or_create_user_id(self.user_code)]).execute()[0]
        return user


class Many(util.NoonBaseModel):
    id_user_list: List[int] = []
    user_code_list: List[str] = []

    def execute(self):
        assert self.id_user_list or self.user_code_list, 'You should provide a list of user ids or codes'
        rows = sql(
            engine,
            '''
            SELECT
                u.code as user_code,
                rr.resource_type,
                rr.role_type,
                ua.resource_ref
            FROM user u
            LEFT JOIN user_access ua USING(id_user)
            LEFT JOIN resource_role rr USING (id_resource_role)
            WHERE TRUE 
            {% if id_user_list %} AND u.id_user IN :id_user_list {% endif %}
            {% if user_code_list %} AND u.code IN :user_code_list {% endif %}
        ''',
            id_user_list=self.id_user_list,
            user_code_list=self.user_code_list,
        ).dicts()

        rows = [
            {
                'user_code': v[0]['user_code'],
                'resources': [
                    UserAccess(
                        resource_type=ResourceType[r['resource_type']],
                        role_type=RoleType[r['role_type']],
                        resource_ref=r['resource_ref'],
                    )
                    for r in v
                ]
                if v[0]['resource_type']
                else [],
            }
            for _, v in miscutil.groupby(rows, lambda x: x['user_code'])
        ]
        for row in rows:
            row['is_platform_admin'] = any(
                resource_role.matches(ua, resource_role.PLATFORM_ADMIN) for ua in row['resources']
            )

        users = [User(**r) for r in rows]
        return users
