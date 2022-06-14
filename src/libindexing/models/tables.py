import sqlalchemy as sa
from sqlalchemy import text, types
from sqlalchemy.dialects import mysql
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.schema import UniqueConstraint
from sqlalchemy.types import UserDefinedType

from libindexing import engine_offer

TINYINT = mysql.TINYINT(unsigned=True)
SMALLINT = mysql.SMALLINT(unsigned=True)
MEDIUMINT = mysql.MEDIUMINT(unsigned=True)
INT = mysql.INTEGER(unsigned=True)
BIGINT = mysql.BIGINT(unsigned=True)
SINT = mysql.INTEGER(unsigned=False)
SBIGINT = mysql.BIGINT(unsigned=False)
CCY = sa.Numeric(13, 2)


def create_all():
    Base.metadata.create_all(engine_offer)


def recreate_all():
    import os

    assert os.getenv('ENV') == 'dev', 'must be dev'
    assert engine_offer.url.username == 'root'
    assert engine_offer.url.password == 'root'
    Base.metadata.drop_all(engine_offer)
    Base.metadata.create_all(engine_offer)


Base = declarative_base()


# These columns should always be at the end of a table
class MixinColumn(sa.Column):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._creation_order = 9000


class POLYGON(UserDefinedType):
    def get_col_spec(self):
        return "POLYGON"


class Model(Base):
    __abstract__ = True
    __bind_key__ = 'boilerplate_offer'

    created_at = MixinColumn(types.TIMESTAMP, server_default=text('CURRENT_TIMESTAMP'), nullable=False)
    updated_at = MixinColumn(types.TIMESTAMP, server_default=text('CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP'),
                             nullable=False)


class OfferStock(Model):
    __tablename__ = 'offer_stock'
    id_offer_stock = sa.Column(BIGINT, primary_key=True)

    sku = sa.Column(sa.String(50), nullable=False, index=True)
    wh_code = sa.Column(sa.String(50), nullable=False)
    country_code = sa.Column(sa.String(2), nullable=False)
    id_partner = sa.Column(INT, nullable=False)
    stock_net = sa.Column(INT, nullable=False, server_default='0')

    __table_args__ = (
        UniqueConstraint('sku', 'wh_code', name='uq_sku_wh'),
    )


class Offer(Model):
    __tablename__ = 'offer'
    id_offer = sa.Column(BIGINT, primary_key=True)

    sku = sa.Column(sa.String(50), nullable=False, index=True)
    wh_code = sa.Column(sa.String(50), nullable=False)
    country_code = sa.Column(sa.String(2), nullable=False)
    id_partner = sa.Column(INT, nullable=False)
    offer_price = sa.Column(CCY, nullable=False, server_default='0')
    msrp = sa.Column(CCY, nullable=True)

    __table_args__ = (
        UniqueConstraint('sku', 'wh_code', name='uq_sku_wh'),
    )
