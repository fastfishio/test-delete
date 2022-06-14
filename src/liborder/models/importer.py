import logging

from boltons import iterutils
from noonutil.v1 import miscutil
from noonutil.v2 import sqlutil

from liborder import ctx, Context, models

logger = logging.getLogger(__name__)


def import_rows_parallel_ignore_error(parallel, key, rows, *, chunk_size=5):
    importer = IMPORTERS.get(key)
    if importer is None:
        raise ValueError(f'unknown importer {key}')
    assert not ctx.get(), 'must not have ctx'

    def process_chunk(chunk):
        with Context.service():
            importer(chunk)

    chunks = list(enumerate(iterutils.chunked(rows, chunk_size)))
    miscutil.process_parallel(parallel, chunks, lambda t: process_chunk(t[1]), lambda t: t[0], logger=logger)


def import_rows(key, rows, *, chunk_size=500):
    importer = IMPORTERS.get(key)
    if importer is None:
        raise ValueError(f'unknown importer {key}')
    if ctx.get():
        for chunk in iterutils.chunked(rows, chunk_size):
            importer(chunk)
        return
    for chunk in iterutils.chunked(rows, chunk_size):
        with Context.service(isolation_level='READ COMMITTED'):
            importer(chunk)


def import_from_test(type, file):
    import json
    import toml
    assert not Context.is_production, 'cant import test data in production'
    if type == 'test_core':
        with open(file, 'r') as fp:
            data = json.load(fp)
        for key, rows in data.items():
            models.importer.import_rows(key, rows)

    if type == 'test_env':
        with open(file, 'rt') as fp:
            data = toml.load(fp)
        for key, rows in data.items():
            models.importer.import_rows(key, rows)


MD_TYPE = ['core', 'env']
if not Context.is_production:
    MD_TYPE += ['test_core', 'test_env']

### IMPORTERS

IMPORTERS = {}


def register(fn):
    IMPORTERS[fn.__name__.replace('import_', '')] = fn
    return fn


@register
def import_warehouse(rows):
    sqlutil.upsert_batch(ctx.conn, models.tables.Warehouse, rows)


@register
def import_cancel_reason(rows):
    sqlutil.upsert_batch(ctx.conn, models.tables.CancelReason, rows)


@register
def import_status(rows):
    sqlutil.upsert_batch(ctx.conn, models.tables.Status, rows)


@register
def import_country(rows):
    sqlutil.upsert_batch(ctx.conn, models.tables.Country, rows)


@register
def import_fleet(rows):
    sqlutil.upsert_batch(ctx.conn, models.tables.Fleet, rows)


@register
def import_warehouse_fleet(rows):
    sqlutil.upsert_batch(ctx.conn, models.tables.WarehouseFleet, rows)


@register
def import_order_cancel_reason(rows):
    sqlutil.upsert_batch(ctx.conn, models.tables.OrderCancelReason, rows)


@register
def import_cs_adjustment_reason(rows):
    sqlutil.upsert_batch(ctx.conn, models.tables.CSAdjustmentReason, rows)
