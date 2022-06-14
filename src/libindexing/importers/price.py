import json
import logging

from boltons import iterutils
from noonutil.v1 import impexutil, miscutil
from noonutil.v2 import sqlutil

from libindexing import engine_offer
from libindexing.importers.enricher import get_enricher
from libindexing.models import tables
from libutil import pubsub


logger = logging.getLogger(__name__)
enricher = get_enricher()

BOILERPLATE_PRICE_UPDATE_TASK_QUEUE = 'boilerplate_price-import-task-list'


# @temporal.activity(task_queue=BOILERPLATE_PRICE_UPDATE_TASK_QUEUE)
async def process_import(code: str, chunk_count: int, import_run_params: dict):
    BoilerplatePriceImport(import_run_params, chunk_count).process()


class BoilerplatePriceImport(impexutil.Importer):
    """
    Boilerplate Marketplace price import
    """

    def preexecute(self):
        valid_rows = self.rows
        invalid_rows = []
        pre_processors = [preprocess_column_types, preprocess_partner, preprocess_partner_sku, preprocess_warehouse]
        if self.rows:
            for pre_processor in pre_processors:
                valid_rows, invalid = pre_processor(valid_rows, self.params)
                invalid_rows += invalid
        self.rows = valid_rows
        self.errors = invalid_rows

    def execute(self):
        if not self.rows:
            return
        # Should we allow MSRP updates? this might be abused by setting high msrp price and normal offer_price
        sqlutil.upsert(
            engine_offer,
            tables.Offer,
            self.rows,
            unique_columns=['sku', 'wh_code'],
            insert_columns=['sku', 'wh_code', 'country_code', 'id_partner', 'offer_price', 'msrp'],
            update_columns=['offer_price', 'msrp'],
        )
        to_publish = [{'sku': row['sku'], 'wh_code': row['wh_code']} for row in self.rows]
        publisher = pubsub.get_publisher('boilerplate_price_update')
        for chunk in iterutils.chunked(to_publish, 20):
            publisher(json.dumps(chunk))


def preprocess_column_types(rows, params=None):
    for row in rows:
        row['id_partner'] = miscutil.safe_int(row['id_partner'])
        if not row['id_partner']:
            row['error_code'] = 'Invalid id_partner'
        row['offer_price'] = util.safe_float(row['offer_price'])
        if not row['offer_price']:
            row['error_code'] = 'Invalid offer_price'
        if 'msrp' not in row:
            row['msrp'] = None
    valid_rows = [row for row in rows if 'error_code' not in row]
    invalid_rows = [row for row in rows if 'error_code' in row]
    return valid_rows, invalid_rows


def preprocess_partner(rows, params=None):
    for row in rows:
        if row['id_partner'] != params['id_partner']:
            row['error_code'] = 'Request id_partner does not match import id_partner'
    valid_rows = [row for row in rows if 'error_code' not in row]
    invalid_rows = [row for row in rows if 'error_code' in row]
    return valid_rows, invalid_rows


def preprocess_partner_sku(rows, params=None):
    for row in rows:
        row['psku_canonical'] = util.canonicalize(row['partner_sku'])
        row['id_partner'] = miscutil.safe_int(row['id_partner'])
    enricher.enrich(
        rows,
        '''
        SELECT dsp.catalog_sku as sku
        FROM r
        LEFT JOIN ds_psku dsp ON (r.id_partner, r.psku_canonical) = (dsp.id_partner, dsp.psku_canonical)
    ''',
    )
    valid_rows = [row for row in rows if row['sku']]
    invalid_rows = [row for row in rows if not row['sku']]
    for row in invalid_rows:
        row['error_code'] = 'Invalid partner sku'
    return valid_rows, invalid_rows


def preprocess_warehouse(rows, params=None):
    for row in rows:
        row['wh_code'] = row['warehouse_code']
    return rows, []


if __name__ == '__main__':
    # asyncio.run(temporal.start_workers(task_queue=BOILERPLATE_PRICE_UPDATE_TASK_QUEUE))
    pass
