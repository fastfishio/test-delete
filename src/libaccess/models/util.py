from libaccess.domain.enums import ResourceType, RoleType
from noonutil.v1 import miscutil
from jsql import sql
from libaccess import engine
from noonutil.v2 import sqlutil
from libutil import util as gutil


def make_get_x_by_y(tbl):
    return sqlutil.make_get_x_by_y(engine, tbl)


@miscutil.cached(ttl=60)
def get_user_id_by_code(code, allow_none=False):
    id_user = sql(
        engine,
        '''
        SELECT id_user
        FROM user
        WHERE code = :code
    ''',
        code=code,
    ).scalar()
    assert allow_none or id_user, f'invalid user code: {code}'
    return id_user


@miscutil.cached(ttl=60)
def get_resource_role_id_by_code(resource_type: ResourceType, role_type: RoleType):
    id_rr = sql(
        engine,
        '''
        SELECT id_resource_role
        FROM resource_role
        WHERE resource_type = :resource_type
        AND role_type = :role_type
    ''',
        resource_type=resource_type.name,
        role_type=role_type.name,
    ).scalar()
    return id_rr


class LibAccessBaseModel(gutil.NoonBaseModel):
    class Config:
        use_enum_values = False


def sanitize_code(code: str) -> str:
    return code.strip().upper()
