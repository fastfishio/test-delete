import sqlalchemy as sa
from sqlalchemy import text, types
from sqlalchemy.dialects import mysql
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.schema import UniqueConstraint

import libcontent

TINYINT = mysql.TINYINT(unsigned=True)
SMALLINT = mysql.SMALLINT(unsigned=True)
MEDIUMINT = mysql.MEDIUMINT(unsigned=True)
INT = mysql.INTEGER(unsigned=True)
BIGINT = mysql.BIGINT(unsigned=True)
SINT = mysql.INTEGER(unsigned=False)
SBIGINT = mysql.BIGINT(unsigned=False)
CCY = sa.Numeric(13, 2)


def create_all():
    Base.metadata.create_all(libcontent.engine)


def recreate_all():
    import os

    assert os.getenv('ENV') == 'dev', 'must be dev'
    assert libcontent.engine.url.username == 'root'
    assert libcontent.engine.url.password == 'root'
    Base.metadata.drop_all(libcontent.engine)
    Base.metadata.create_all(libcontent.engine)


Base = declarative_base()


# These columns should always be at the end of a table
class MixinColumn(sa.Column):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._creation_order = 9000


class Model(Base):
    __abstract__ = True

    created_at = MixinColumn(types.TIMESTAMP, server_default=text('CURRENT_TIMESTAMP'), nullable=False)
    updated_at = MixinColumn(
        types.TIMESTAMP, server_default=text('CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP'), nullable=False
    )


class Page(Model):
    __tablename__ = 'page'
    id_page = sa.Column(BIGINT, primary_key=True)
    code = sa.Column(sa.String(50), nullable=False)  # e.g. home_app_mobile_ae, no_service_app_mobile_ae
    type = sa.Column(sa.String(50), nullable=False)  # e.g. home, no_service
    country_code = sa.Column(sa.String(2), nullable=False)  # e.g. ae, sa
    platform = sa.Column(sa.String(50), nullable=False)  # e.g. web, app
    content_type = sa.Column(sa.String(50), nullable=False)  # e.g. mobile, desktop
    updated_by = sa.Column(sa.String(50), nullable=False)
    __table_args__ = (
        UniqueConstraint('type', 'country_code', 'platform', 'content_type', name='uq_combination'),
        UniqueConstraint('code', name='uq_code'),
    )


class Widget(Model):
    __tablename__ = 'widget'
    id_widget = sa.Column(BIGINT, primary_key=True)
    code = sa.Column(sa.String(50), nullable=False)  # e.g. widget_1, widget_2
    page_code = sa.Column(sa.String(50), nullable=False)  # foreign key from 'page' table
    type = sa.Column(sa.String(50), nullable=False)  # widget type. e.g. bannerModuleStrip, bannerSlider
    position = sa.Column(INT, nullable=False)  # relative to other widgets within the same page, ascending order
    title_en = sa.Column(sa.String(200), nullable=True)
    title_ar = sa.Column(sa.String(200), nullable=True)
    title_color = sa.Column(sa.String(10), nullable=True)
    product_url = sa.Column(sa.String(1000), nullable=True)
    num_per_row = sa.Column(sa.String(200), nullable=True)  # widget property - number of items in a single row
    build_ge = sa.Column(INT, nullable=True)
    is_active = sa.Column(TINYINT, nullable=False)
    misc = sa.Column(sa.String(2000), nullable=True)
    updated_by = sa.Column(sa.String(50), nullable=False)
    __table_args__ = (UniqueConstraint('code', name='uq_code'),)


class Asset(Model):
    __tablename__ = 'asset'
    id_asset = sa.Column(BIGINT, primary_key=True)
    code = sa.Column(sa.String(50), nullable=False)  # e.g. asset_1, asset_2
    widget_code = sa.Column(sa.String(50), nullable=False)
    position = sa.Column(INT, nullable=False)  # relative to other assets within the same widget, ascending order
    link = sa.Column(sa.String(1000), nullable=True)
    image_en = sa.Column(sa.String(200), nullable=True)
    image_ar = sa.Column(sa.String(200), nullable=True)
    start_date = sa.Column(types.TIMESTAMP, nullable=True)  # time interval for which this asset is effective
    end_date = sa.Column(types.TIMESTAMP, nullable=True)  # time interval for which this asset is effective
    is_active = sa.Column(TINYINT, nullable=False)
    criteria = sa.Column(sa.String(2000), nullable=True)
    misc = sa.Column(sa.String(2000), nullable=True)
    updated_by = sa.Column(sa.String(50), nullable=False)
    __table_args__ = (UniqueConstraint('code', name='uq_code'),)
