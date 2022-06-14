import logging
import os
from enum import Enum

from boltons import iterutils
from noonutil.v1 import spannerutil
from retrying import retry

IS_PRODUCTION = os.getenv('ENV') not in ('dev', 'staging')

BOILERPLATE_SPANNER_INSTANCE_ID = os.getenv('BOILERPLATE_SPANNER_INSTANCE_ID')
BOILERPLATE_SPANNER_DATABASE_ID = os.getenv('BOILERPLATE_SPANNER_DATABASE_ID')
BOILERPLATE_SPANNER_PROJECT = os.getenv('BOILERPLATE_SPANNER_PROJECT')

NOON_SPANNER_INSTANCE_ID = os.getenv('NOON_SPANNER_INSTANCE_ID')
NOON_SPANNER_DATABASE_ID = os.getenv('NOON_SPANNER_DATABASE_ID')
NOON_SPANNER_PROJECT = os.getenv('NOON_SPANNER_PROJECT')

IS_TESTING = os.getenv('TESTING') == 'pytest'

logger = logging.getLogger(__name__)


class SpannerBaseModel(Enum):

    @classmethod
    def get_fields(cls):
        for attr in cls.__members__.keys():
            # Ignore Private variables
            if attr[0] != '_':
                yield attr

    @classmethod
    def get_values(cls, values_list):
        for values in values_list:
            row = []
            for attr, _type in cls.__members__.items():
                # Ignore Private variables
                if attr[0] == '_':
                    continue
                val = values.get(attr)
                try:
                    val = _type.value.type(val) if val is not None else _type.value.null
                except Exception as e:
                    logger.warning("SpannerBaseModel type error {0} {1} {2} {3}".format(
                        cls, e, attr, val))
                    val = _type.value.default
                row.append(val)
            yield row

    @classmethod
    @retry(stop_max_attempt_number=3, wait_fixed=50)
    def _upsert(cls, connection, table_name, values_list):
        connection.insert_or_update(table_name, cls.get_fields(), cls.get_values(values_list))

    @classmethod
    def upsert(cls, connection, table_name, values_list):
        for chunk in iterutils.chunked(values_list, 500):
            cls._upsert(connection, table_name, chunk)


def get_spanner_db(spanner_project_name, spanner_instance_id, spanner_database_id):
    return spannerutil.SpannerDB(
        spanner_project_name, spanner_instance_id, spanner_database_id,
        pool_size=20, default_timeout=10, custom_pool_ping=False
    )


def boilerplate_spanner():
    return get_spanner_db(BOILERPLATE_SPANNER_PROJECT, BOILERPLATE_SPANNER_INSTANCE_ID, BOILERPLATE_SPANNER_DATABASE_ID)


def sc_spanner():
    return get_spanner_db(NOON_SPANNER_PROJECT, NOON_SPANNER_INSTANCE_ID, NOON_SPANNER_DATABASE_ID)


def noon_cache_spanner():
    return get_spanner_db(NOON_SPANNER_PROJECT, NOON_SPANNER_INSTANCE_ID, "cache")
