import os
from typing import Dict, List
from jsql import sql
from libaccess.domain import permission
from libaccess.domain.enums import Permission, ResourceType, RoleType
from noonutil.v1 import miscutil
from noonutil.v2 import sqlutil
from boltons import iterutils
import logging
from libaccess import ctx, Context, models, domain, engine
from libaccess.models import util
import json

logger = logging.getLogger(__name__)


def import_rows(key, rows, *, chunk_size=500):
    importer = IMPORTERS.get(key)
    assert importer, f'unknown importer {key}'

    if ctx.get():
        for chunk in iterutils.chunked(rows, chunk_size):
            importer(chunk)
        return

    for chunk in iterutils.chunked(rows, chunk_size):
        with Context.service(isolation_level='READ COMMITTED'):
            importer(chunk)


def import_from_index(index, key_pattern):
    import re

    for k, v in index.items():
        if re.search(key_pattern, k):
            rows = read_google_doc(v)
            logger.info(f'importing {k} ({len(rows)}) from {v}')
            import_rows(k, rows)


def import_from_test(link):
    import toml

    assert not Context.is_production, 'cant import test data in production'

    with open(link, 'rt') as fp:
        data = toml.load(fp)
    for key, rows in data.items():
        models.importer.import_rows(key, rows)


@miscutil.cached(ttl=60)
def get_index(type):
    link = os.environ['MASTER_DATA_' + type]
    return get_index_helper(link)


def read_google_doc(url):
    return miscutil.read_google_doc(url)


def get_index_helper(link):
    rows = read_google_doc(link)
    return {r['key']: r['link'] for r in rows}


### IMPORTERS

IMPORTERS = {}


def register(fn):
    IMPORTERS[fn.__name__.replace('import_', '')] = fn
    return fn


@register
def import_access_resource_role(rows: List[Dict[str, str]]):
    valid_permissions = [p.name for p in Permission]
    valid_role_types = [rt.name for rt in RoleType]
    valid_resource_types = [rt.name for rt in ResourceType]

    for row in rows:
        assert 'name' in row

        permissions = util.sanitize_code(row['permissions']).split('|') if row['permissions'] else []
        assert all(p in valid_permissions for p in permissions), f"Invalid permissions for resource role: {row['name']}"
        row['permissions'] = json.dumps(permissions)

        row['resource_type'] = util.sanitize_code(row['resource_type'])
        assert row['resource_type'] in valid_resource_types, f"Invalid resource type for resource role: {row['name']}"

        row['role_type'] = util.sanitize_code(row['role_type'])
        assert row['role_type'] in valid_role_types, f"Invalid role type for resource role: {row['name']}"

        row['role_desc'] = row.get('role_desc') or ''
    sqlutil.upsert(
        engine,
        models.tables.ResourceRole,
        rows,
        unique_columns=['resource_type', 'role_type'],
        update_columns=['name', 'role_desc', 'permissions'],
    )


@register
def import_access_user_resource(rows: List[Dict[str, str]]):
    for row in rows:
        row['id_resource_role'] = models.util.get_resource_role_id_by_code(
            resource_type=ResourceType[util.sanitize_code(row['resource_type'])],
            role_type=RoleType[util.sanitize_code(row['role_type'])],
        )
        row['id_user'] = domain.user.get_or_create_user_id(util.sanitize_code(row['user_code']))
        row['resource_ref'] = util.sanitize_code(row['resource_ref'])
    sqlutil.upsert(
        engine, models.tables.UserAccess, rows, unique_columns=['id_user', 'id_resource_role', 'resource_ref']
    )


@register
def import_access_customer_service_user(rows: List[Dict[str, str]]):
    for row in rows:
        row['id_user'] = domain.user.get_or_create_user_id(util.sanitize_code(row['email']))
        row['id_resource_role'] = models.util.get_resource_role_id_by_code(
            resource_type=domain.enums.ResourceType.CUSTOMER_SERVICE,
            role_type=RoleType[util.sanitize_code(row['team'])],
        )
        row['resource_ref'] = 'NOON_CS'
    sql(
        ctx.conn,
        '''
        DELETE ua
        FROM user_access ua
        LEFT JOIN resource_role rr USING(id_resource_role)
        WHERE ua.id_user IN :id_user_list
        AND rr.resource_type = :resource_type
    ''',
        id_user_list=[r['id_user'] for r in rows],
        resource_type=ResourceType.CUSTOMER_SERVICE.name,
    )
    sqlutil.upsert(
        ctx.conn, models.tables.UserAccess, rows, unique_columns=['id_user', 'id_resource_role', 'resource_ref']
    )
