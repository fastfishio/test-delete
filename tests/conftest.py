import logging
import os
from unittest import mock

import pytest
import requests
from noonutil.v1 import spannertestkit, engineutil

from libutil import engines
from tests import load_fixtures

logger = logging.getLogger(__name__)
pytest.register_assert_rewrite('noonutil.v1.fastapiutil')

SOLR_HOST = "solr"


def index_solr_data():
    assert os.getenv('ENV') == "dev", 'must be dev'
    resp = requests.get(
        f"http://{SOLR_HOST}:8983/solr/offer_ae/update" + "?stream.body=<delete><query>*:*</query></delete>&commit=true"
    )
    with open("/src/tests/catalog/data/offers.json", "r") as f:
        import json

        offers = json.loads(f.read())
        resp = requests.post(f"http://{SOLR_HOST}:8983/solr/offer_ae/update?commit=true", json=offers)


def setup_engine_env():
    assert os.getenv('ENV') in ('dev', 'staging'), 'must be dev/stg'

    with engines.get_engine(engines.BASE_ENGINE_NAME).connect() as test_conn:
        for engine_name, engine_config in engineutil.ENGINE_CONFIGS.items():
            if engine_name == engines.BASE_ENGINE_NAME:
                continue

            db_name = (
                engine_config.path[1:]
                if isinstance(engine_config, engineutil.EngineConfigurationStandard)
                else engine_config.default_database
            )
            logger.info(f'Setting up Engine: {engine_name}\tDb: {db_name}')
            test_conn.execute(f'DROP DATABASE IF EXISTS {db_name}')
            test_conn.execute(f'CREATE DATABASE {db_name}')


setup_engine_env()


def setup_solr_schema():
    assert os.getenv('ENV') == "dev", 'must be dev'

    resp = requests.get(f"http://{SOLR_HOST}:8983/solr/offer_ae/schema/fields")

    if resp.status_code != 200:
        # push relevant field to outlet schema
        create_core_response = requests.get(
            f"http://{SOLR_HOST}:8983/solr/admin/cores?action=CREATE&name=offer_ae&instanceDir=offer_ae&configSet=managed-base&schema=schema.xml"
        )
        create_core_response.raise_for_status()
        with open("/src/tests/catalog/solr_schema/offer.json", "r") as f:
            schema = f.read()
        resp = requests.post(f"http://{SOLR_HOST}:8983/solr/offer_ae/schema", data=schema)
        logger.info("schema create response solr", resp.json())
    index_solr_data()


@pytest.fixture(scope="session", autouse=True)
def app_catalog(data_servicability):
    from appcatalog.web import app
    from fastapi.testclient import TestClient

    client = TestClient(app)
    setup_solr_schema()
    yield client


@pytest.fixture(scope="session", autouse=True)
def mock_payment():
    from tests.order.mocks.payment import MockPayment

    with mock.patch('libexternal.Payment', new_callable=MockPayment) as payment_mock:
        yield payment_mock


@pytest.fixture(scope="session", autouse=True)
def mock_credit():
    from tests.order.mocks.credit import MockCredit

    with mock.patch('libexternal.Credit', new_callable=MockCredit) as credit_mock:
        yield credit_mock


@pytest.fixture(scope="session", autouse=True)
def app_order(data_order):
    from apporder.web import app
    from fastapi.testclient import TestClient

    client = TestClient(app)
    yield client


@pytest.fixture(scope="session", autouse=True)
def setup_spanner():
    spanner_client = spannertestkit.get_client(host=os.getenv('SPANNER_EMULATOR_HOST'), project='noon-test')

    spannertestkit.create_db(
        spanner_client,
        os.getenv('BOILERPLATE_SPANNER_INSTANCE_ID'),
        os.getenv('BOILERPLATE_SPANNER_DATABASE_ID'),
        "/src/tests/data/spanner/boilerplate.toml",
    )

    spannertestkit.create_db(
        spanner_client,
        os.getenv('NOON_SPANNER_INSTANCE_ID'),
        os.getenv('NOON_SPANNER_DATABASE_ID'),
        "/src/tests/data/spanner/scstock.toml",
    )

    spannertestkit.create_db(
        spanner_client, os.getenv('NOON_SPANNER_INSTANCE_ID'), "cache", "/src/tests/data/spanner/cache.toml"
    )


@pytest.fixture(scope="session", autouse=True)
def engine_order():
    engine = engines.get_engine('boilerplate_order')
    assert engines.get_engine_selected_db(engine) == 'boilerplate_order'
    import liborder

    liborder.models.tables.recreate_all()
    return engine


@pytest.fixture(scope="session", autouse=True)
def engine_access():
    engine = engines.get_engine('boilerplate_access')
    assert engines.get_engine_selected_db(engine) == 'boilerplate_access'
    import libaccess

    libaccess.models.tables.recreate_all()
    return engine


@pytest.fixture(scope="session", autouse=True)
def engine_content():
    engine = engines.get_engine('boilerplate_content')
    assert engines.get_engine_selected_db(engine) == 'boilerplate_content'
    import libcontent

    libcontent.models.tables.recreate_all()
    return engine


@pytest.fixture(scope="session", autouse=True)
def engine_noon_patalog():
    engine = engines.get_engine('noon_patalog')
    assert engines.get_engine_selected_db(engine) == 'patalog'
    import libindexing

    libindexing.models.external_tables.recreate_all()
    return engine


@pytest.fixture(scope="session", autouse=True)
def engine_noon_mp_cache_ro():
    engine = engines.get_engine('noon_mp_cache_ro')
    assert engines.get_engine_selected_db(engine) == 'psku'
    import libindexing

    libindexing.models.cache_tables.recreate_all()
    return engine


@pytest.fixture(scope="session", autouse=True)
def engine_offer():
    from libutil import util

    engine = engines.get_engine('boilerplate_offer')
    assert engines.get_engine_selected_db(engine) == 'boilerplate_offer'
    import libindexing

    libindexing.models.tables.recreate_all()
    return engine


@pytest.fixture(scope="session", autouse=True)
def engine_noon_catalog():
    engine = engines.get_engine('noon_catalog')
    assert engines.get_engine_selected_db(engine) == 'wecat_md'
    import libcatalog

    libcatalog.models.external_tables.recreate_all()
    return engine


@pytest.fixture(scope="session", autouse=True)
def data_noon_catalog(engine_noon_catalog):
    from libcatalog import models

    load_fixtures.load_fixtures(
        "/src/tests/catalog/data/external_env.toml", engine_noon_catalog, models.external_tables
    )
    return 1


@pytest.fixture(scope="session", autouse=True)
def data_access(engine_access):
    from libaccess import models

    models.importer.import_from_test('/src/tests/access/data/env.toml')
    return 1


@pytest.fixture(scope="session")
def data_order(engine_order):
    from liborder import models

    load_fixtures.load_fixtures("/src/tests/order/data/fixture.toml", engine_order, models.tables)
    models.importer.import_from_test('test_env', '/src/tests/order/data/env.toml')
    return 1


@pytest.fixture(scope="session")
def data_servicability(engine_order):
    from liborder import models

    load_fixtures.load_fixtures("/src/tests/order/data/fixture.toml", engine_order, models.tables)
    models.importer.import_from_test('test_env', '/src/tests/data/serviceability.toml')
    return 1


@pytest.fixture(scope="session")
def data_indexing(engine_offer):
    from libindexing import models

    load_fixtures.load_fixtures("/src/tests/indexing/data/fixture.toml", engine_offer, models.tables)
    return 1


@pytest.fixture(scope="session", autouse=True)
def data_cache(engine_noon_mp_cache_ro):
    from libindexing import models

    load_fixtures.load_fixtures(
        "/src/tests/indexing/data/cache_fixture.toml", engine_noon_mp_cache_ro, models.cache_tables
    )
    return 1


@pytest.fixture(scope='session')
def data_noon_patalog(engine_noon_patalog):
    from libindexing import models

    load_fixtures.load_fixtures(
        "/src/tests/indexing/data/external_fixture.toml", engine_noon_patalog, models.external_tables
    )


@pytest.fixture(scope="session", autouse=True)
def engine_catalog():
    from libutil import util

    engine = engines.get_engine('boilerplate_catalog')
    assert engines.get_engine_selected_db(engine) == 'boilerplate_catalog'
    import libcatalog

    libcatalog.models.tables.recreate_all()
    return engine


@pytest.fixture(scope="session", autouse=True)
def data_catalog(engine_catalog):
    from libcatalog.models import tables

    load_fixtures.load_fixtures("/src/tests/catalog/data/env.toml", engine_catalog, tables)
    return 1


@pytest.fixture(scope="session", autouse=True)
def data_content(engine_content):
    from libcontent.models import tables

    load_fixtures.load_fixtures("/src/tests/content/data/env.toml", engine_content, tables)
    return 1


@pytest.fixture(scope="session", autouse=True)
def app_cs(data_order):
    from appcs.web import app
    from fastapi.testclient import TestClient

    client = TestClient(app)
    yield client


@pytest.fixture(scope="session", autouse=True)
def app_team():
    from appteam.web import app
    from fastapi.testclient import TestClient

    client = TestClient(app)
    yield client
