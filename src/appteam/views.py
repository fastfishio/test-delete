import json
import logging

from boltons import iterutils
from fastapi import APIRouter
from jsql import sql

import libaccess.models.tables
from appteam.web import g
from libindexing.domain.stock import full_stock_update_for_warehouse
from liborder import Context
from libutil import pubsub

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post('/import/{db}/{importer}/{table}/execute', tags=['import'])
def execute_import(db, importer, table):
    if db == 'catalog':
        from libcatalog import models, engine
    else:
        assert False, 'invalid db'
    if importer.startswith('boilerplate_'):
        importer = importer.replace('boilerplate_', '')
    rows = sql(engine, 'SELECT * FROM tmp_loader.{{ table }} LIMIT 10001', table=table).dicts()
    assert len(rows) <= 10000, 'max 10k rows'
    models.importer.import_rows(importer, rows, g.user_code)
    return 'done'


@router.get('/sync_stock/{wh_code}', tags=['sync'])
def sync_stock(wh_code):
    try:
        logger.warning(f"full stock update for wh_code: {wh_code} started")
        full_stock_update_for_warehouse(wh_code)
    except Exception as ex:
        return {'error': f'{ex}'}
    return 'ok'


@router.get('/sync_products/{zsku_list}', tags=['sync'])
def sync_products(zsku_list):
    zsku_list = zsku_list.split(',')
    if not zsku_list:
        return
    publisher = pubsub.get_publisher('boilerplate_reindex_sku')
    for chunk in iterutils.chunked(zsku_list, 200):
        publisher(json.dumps(chunk))
    return 'published to topic: boilerplate_reindex_sku'


@router.get('/import/access-control', tags=['import'])
def import_access_control(clear: bool = False):
    from libaccess import models

    if clear:
        libaccess.models.tables.clear_db()

    ix = models.importer.get_index('access')
    models.importer.import_from_index(ix, 'access')
    return "ok"
