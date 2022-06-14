import sqlalchemy as sa
from sqlalchemy import text, types
from sqlalchemy.dialects import mysql
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.schema import UniqueConstraint

from libindexing import engine_noon_patalog

TINYINT = mysql.TINYINT(unsigned=True)
SMALLINT = mysql.SMALLINT(unsigned=True)
MEDIUMINT = mysql.MEDIUMINT(unsigned=True)
INT = mysql.INTEGER(unsigned=True)
BIGINT = mysql.BIGINT(unsigned=True)
SINT = mysql.INTEGER(unsigned=False)
SBIGINT = mysql.BIGINT(unsigned=False)
CCY = sa.Numeric(13, 2)


def create_all():
    Base.metadata.create_all(engine_noon_patalog)


def recreate_all():
    import os

    assert os.getenv('ENV') == 'dev', 'must be dev'
    assert engine_noon_patalog.url.username == 'root'
    assert engine_noon_patalog.url.password == 'root'
    Base.metadata.drop_all(engine_noon_patalog)
    Base.metadata.create_all(engine_noon_patalog)


Base = declarative_base()


# These columns should always be at the end of a table
class MixinColumn(sa.Column):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._creation_order = 9000


class Model(Base):
    __abstract__ = True
    __bind_key__ = 'patalog'

    created_at = MixinColumn(types.TIMESTAMP, server_default=text('CURRENT_TIMESTAMP'), nullable=False, index=True)
    updated_at = MixinColumn(
        types.TIMESTAMP,
        server_default=text('CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP'),
        nullable=False,
        index=True,
    )


class Psku(Model):
    __tablename__ = 'psku'
    id_psku = sa.Column(BIGINT, primary_key=True)
    psku_code = sa.Column(sa.String(100), nullable=False, unique=True)
    id_partner = sa.Column(INT, nullable=False)
    psku_canonical = sa.Column(sa.String(100), nullable=False)
    partner_sku = sa.Column(sa.String(100), nullable=False)
    is_active = sa.Column(TINYINT, nullable=False, server_default='0')
    updated_by = sa.Column(sa.String(100), nullable=False, server_default='')


class PskuCatalogMap(Model):
    __tablename__ = 'psku_catalog_map'
    id_psku_catalog_map = sa.Column(BIGINT, primary_key=True)
    psku_code = sa.Column(sa.String(100), nullable=False)
    id_catalog = sa.Column(INT, nullable=False)
    id_partner = sa.Column(INT, nullable=False)
    catalog_sku = sa.Column(sa.String(100), nullable=False)
    __table_args__ = (UniqueConstraint('psku_code', 'id_catalog', name='uq_psku_catalog'),)
