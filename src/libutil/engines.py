import os
from noonutil.v1 import engineutil
from sqlalchemy.engine import Engine
from jsql import sql

# For better insights on this file you can review:
# https://github.com/fastfishio/python-noonutil/blob/master/docs/v1/engineutil.md


class Conn:
    engine_name: str
    secret_user: str
    secret_key: str
    instance: str
    db: str
    db_driver: str = 'mysql+mysqldb'
    external: bool

    def __init__(
        self,
        engine_name: str,
        secret_user: str = 'secretmanager',
        secret_key: str = '',
        instance: str = '',
        db: str = '',
        external: bool = False,
    ):
        self.engine_name = engine_name
        self.secret_user = secret_user
        self.secret_key = secret_key or engine_name
        self.instance = instance or engine_name
        self.db = db
        self.external = external

    def get_connection_string(self, dev: bool = False):
        if dev:
            # overwrite for dev
            self.secret_user = 'root'
            self.secret_key = 'root'
            self.instance = 'mysql8.default.svc.cluster.local'

        return f'{self.db_driver}://{self.secret_user}:{self.secret_key}@{self.instance}/{self.db}'


BASE_ENGINE_NAME = 'base'
# new connection of db should only be added here
ENGINE_CONNECTIONS = [
    # Base
    Conn(engine_name=BASE_ENGINE_NAME, secret_key='mpboilerplate', instance='db-mpboilerplate'),

    # Internal, will be using shared pool of base
    # Define `engine_name` and `db` only
    Conn(engine_name='boilerplate_order', db='boilerplate_order'),
    Conn(engine_name='boilerplate_catalog', db='boilerplate_catalog'),
    Conn(engine_name='boilerplate_access', db='boilerplate_access'),
    Conn(engine_name='boilerplate_offer', db='boilerplate_offer'),
    Conn(engine_name='boilerplate_content', db='boilerplate_content'),

    # External
    Conn(engine_name='noon_mp_cache_ro', secret_key='psku', instance='db-psku', db='psku', external=True),
    Conn(engine_name='noon_catalog', secret_key='catalog', instance='db-catalog', db='wecat_md', external=True),
    Conn(engine_name='noon_patalog', secret_key='patalog', instance='db-patalog', db='patalog', external=True),
]


def get_engine_selected_db(engine: Engine) -> str:
    with engine.connect():
        return sql(engine, 'SELECT DATABASE();').scalar()


def get_engine(name: str) -> Engine:
    return engineutil.get_engine(name)


def __configure_default_engine():
    engineutil.update_engine(
        '_default',
        scheme='mysql+mysqldb',
        query_dict={'charset': 'utf8'},
        create_engine_kwargs={'pool_pre_ping': True, 'pool_size': 4, 'pool_recycle': 600},
    )


def __define_engines():
    is_dev = os.getenv('ENV') == 'dev'

    for conn in ENGINE_CONNECTIONS:
        if conn.engine_name == BASE_ENGINE_NAME or (conn.external and not is_dev):
            # only define engine for BASE, or external engine in stg/prod
            engineutil.define_engine(conn.engine_name, conn.get_connection_string(dev=is_dev))
        else:
            # the rest (internal / external-in-dev), will only use the BASE pool
            engineutil.define_engine_with_shared_pool(
                conn.engine_name, pool_engine=BASE_ENGINE_NAME, default_database=conn.db
            )


def __instrument_engines():
    if os.getenv('TESTING') is None:
        return

    from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
    from libutil import tracer

    for engine_name, engine_config in engineutil.ENGINE_CONFIGS.items():
        if not isinstance(engine_config, engineutil.EngineConfigurationStandard):
            continue
        SQLAlchemyInstrumentor().instrument(engine=get_engine(engine_name), tracer_provider=tracer.tracer_provider)


# Main
__configure_default_engine()
__define_engines()
__instrument_engines()
