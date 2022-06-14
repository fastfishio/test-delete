import logging

import sqlalchemy
from boltons import iterutils
from noonutil.v2 import sqlutil

logger = logging.getLogger(__name__)


def load_fixtures(file, engine, tables, chunk_size=500):
    import toml
    with open(file, 'rt') as fp:
        data = toml.load(fp)
    for key, rows in data.items():
        for row in rows:
            for row_key in row:
                if row[row_key] == '__None__':
                    row[row_key] = None
        do_import(engine, key, rows, tables, chunk_size)


def do_import(engine, key, rows, tables, chunk_size=500):
    table = getattr(tables, key, None)
    unique_columns = getattr(table, 'unique_columns', None) or get_unique_columns(table) or [
        get_primary_key_column_name(table)]
    if not (table and unique_columns):
        logger.error("No unique_columns/UniqueConstraint found for table %s", key)
        raise Exception
    for chunk in iterutils.chunked(rows, chunk_size):
        with engine.begin() as conn:
            sqlutil.upsert(conn, table, chunk, unique_columns=unique_columns, insert_columns=chunk[0].keys())


def get_unique_columns(table, unique_constraint=sqlalchemy.sql.schema.UniqueConstraint):
    table_constraints = list(table.__table__.constraints)
    if not table_constraints:
        return
    props = [a for a in table_constraints if type(a) == unique_constraint]
    if not props:
        return
    return props[0].columns.keys()


def get_primary_key_column_name(table):
    from sqlalchemy import inspect
    return inspect(table).primary_key[0].key
