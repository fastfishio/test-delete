import sqlalchemy as sa
from sqlalchemy.dialects import mysql
from sqlalchemy.ext.declarative import declarative_base

from libindexing import engine_noon_cache

TINYINT = mysql.TINYINT(unsigned=True)
SMALLINT = mysql.SMALLINT(unsigned=True)
MEDIUMINT = mysql.MEDIUMINT(unsigned=True)
INT = mysql.INTEGER(unsigned=True)
BIGINT = mysql.BIGINT(unsigned=True)
SINT = mysql.INTEGER(unsigned=False)
SBIGINT = mysql.BIGINT(unsigned=False)
CCY = sa.Numeric(13, 2)


def create_all():
    Base.metadata.create_all(engine_noon_cache)


def recreate_all():
    import os

    assert os.getenv('ENV') == 'dev', 'must be dev'
    assert engine_noon_cache.url.username == 'root'
    assert engine_noon_cache.url.password == 'root'
    Base.metadata.drop_all(engine_noon_cache)
    Base.metadata.create_all(engine_noon_cache)


Base = declarative_base()


# These columns should always be at the end of a table
class MixinColumn(sa.Column):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._creation_order = 9000


class Model(Base):
    __abstract__ = True
    __bind_key__ = 'psku'


class Psku(Model):
    __tablename__ = 'psku'
    id_psku = sa.Column(BIGINT, primary_key=True)
    psku_code = sa.Column(sa.String(100), nullable=False, unique=True)
    id_partner = sa.Column(INT, nullable=False)
    psku_canonical = sa.Column(sa.String(100), nullable=False)
    partner_sku = sa.Column(sa.String(100), nullable=False)
    zsku_parent = sa.Column(sa.String(100), nullable=True)
    zsku_child = sa.Column(sa.String(100), nullable=True)
    zsku_group = sa.Column(sa.String(100), nullable=True)
    nsku_child = sa.Column(sa.String(100), nullable=True)

    is_active = sa.Column(TINYINT, nullable=False, server_default='1')
