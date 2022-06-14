from jsql import sql
from noonutil.v2 import sqlutil

from liborder.models.tables import *
from libutil.engines import get_engine

ENGINE_boilerplate = get_engine('old')

ENGINE_boilerplate8 = get_engine('new')


def run():
    rows = sql(
        ENGINE_boilerplate,
        '''
        SELECT * 
        FROM boilerplate_order.order_eta_history
    ''',
    ).dicts()
    sqlutil.upsert_batch(ENGINE_boilerplate8, OrderEtaHistory, rows)


if __name__ == "__main__":
    run()
