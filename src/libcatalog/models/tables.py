import sqlalchemy as sa
from sqlalchemy import text, types
from sqlalchemy.dialects import mysql
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.schema import UniqueConstraint

import libcatalog

TINYINT = mysql.TINYINT(unsigned=True)
SMALLINT = mysql.SMALLINT(unsigned=True)
MEDIUMINT = mysql.MEDIUMINT(unsigned=True)
INT = mysql.INTEGER(unsigned=True)
BIGINT = mysql.BIGINT(unsigned=True)
SINT = mysql.INTEGER(unsigned=False)
SBIGINT = mysql.BIGINT(unsigned=False)
NUMERIC = sa.Numeric(8, 2)


def create_all():
    Base.metadata.create_all(libcatalog.engine)


def recreate_all():
    import os

    assert os.getenv('ENV') == 'dev', 'must be dev'
    assert libcatalog.engine.url.username == 'root'
    assert libcatalog.engine.url.password == 'root'
    Base.metadata.drop_all(libcatalog.engine)
    Base.metadata.create_all(libcatalog.engine)


Base = declarative_base()


# These columns should always be at the end of a table
class MixinColumn(sa.Column):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._creation_order = 9000


class Model(Base):
    __abstract__ = True

    created_at = MixinColumn(types.TIMESTAMP, server_default=text('CURRENT_TIMESTAMP'), nullable=False)
    updated_at = MixinColumn(types.TIMESTAMP, server_default=text('CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP'),
                             nullable=False)


class Category(Model):
    __tablename__ = 'category'
    id_category = sa.Column(BIGINT, primary_key=True)
    id_category_parent = sa.Column(INT, nullable=True)
    code = sa.Column(sa.String(50), nullable=False)
    en_name = sa.Column(sa.String(150), nullable=False)
    ar_name = sa.Column(sa.String(150), nullable=False)
    updated_by = sa.Column(sa.String(50), nullable=False)
    __table_args__ = (
        UniqueConstraint('code', name='uq_code'),
    )


class ProductCategory(Model):
    __tablename__ = 'product_category'
    id_product_category = sa.Column(BIGINT, primary_key=True)
    sku = sa.Column(sa.String(50), nullable=False)
    id_category = sa.Column(INT, nullable=True)
    updated_by = sa.Column(sa.String(50), nullable=False)
    __table_args__ = (
        UniqueConstraint('sku', 'id_category', name='uq_sku_category'),
    )


class ProductGroupCode(Model):
    __tablename__ = 'product_group_code'
    id_product_group_code = sa.Column(BIGINT, primary_key=True)
    sku = sa.Column(sa.String(50), nullable=False, index=True)
    group_code = sa.Column(sa.String(50), nullable=True)
    updated_by = sa.Column(sa.String(50), nullable=False)
    __table_args__ = (
        UniqueConstraint('sku', name='uq_sku'),
    )


class ProductMeta(Model):
    __tablename__ = 'product_meta'
    id_product = sa.Column(BIGINT, primary_key=True)
    sku = sa.Column(sa.String(50), nullable=False)
    volume = sa.Column(NUMERIC, nullable=True)
    weight = sa.Column(NUMERIC, nullable=True)
    updated_by = sa.Column(sa.String(50), nullable=False, server_default='')
    __table_args__ = (
        UniqueConstraint('sku', name='uq_sku'),
    )
