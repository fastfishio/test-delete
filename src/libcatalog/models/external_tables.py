import sqlalchemy as sa
from sqlalchemy import text, types
from sqlalchemy.dialects import mysql
from sqlalchemy.ext.declarative import declarative_base

import libcatalog

TINYINT = mysql.TINYINT(unsigned=True)
SMALLINT = mysql.SMALLINT(unsigned=True)
MEDIUMINT = mysql.MEDIUMINT(unsigned=True)
INT = mysql.INTEGER(unsigned=True)
BIGINT = mysql.BIGINT(unsigned=True)
SINT = mysql.INTEGER(unsigned=False)
SBIGINT = mysql.BIGINT(unsigned=False)
CCY = sa.Numeric(13, 2)


def create_all():
    Base.metadata.create_all(libcatalog.engine_noon_catalog)


def recreate_all():
    import os

    assert os.getenv('ENV') == 'dev', 'must be dev'
    assert libcatalog.engine_noon_catalog.url.username == 'root'
    assert libcatalog.engine_noon_catalog.url.password == 'root'
    Base.metadata.drop_all(libcatalog.engine_noon_catalog)
    Base.metadata.create_all(libcatalog.engine_noon_catalog)


Base = declarative_base()


# These columns should always be at the end of a table
class MixinColumn(sa.Column):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._creation_order = 9000


class Model(Base):
    __abstract__ = True

    created_at = MixinColumn(types.TIMESTAMP, server_default=text('CURRENT_TIMESTAMP'), nullable=False, index=True)
    updated_at = MixinColumn(types.TIMESTAMP, server_default=text('CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP'),
                             nullable=False, index=True)


class Brand(Model):
    __tablename__ = 'brand'
    id_brand = sa.Column(BIGINT, primary_key=True)
    is_visible = sa.Column(TINYINT, nullable=False)
    code = sa.Column(sa.String(100), unique=True, nullable=False)
    name_en = sa.Column(sa.String(100), nullable=True)
    name_ar = sa.Column(sa.String(100), nullable=True)
