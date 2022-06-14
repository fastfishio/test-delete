from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import text, types
from sqlalchemy.dialects import mysql
from sqlalchemy.schema import UniqueConstraint, Index
import sqlalchemy as sa
from libaccess.domain import enums
from jsql import sql
import libaccess
import logging

logger = logging.Logger(__file__)


def create_all():
    Base.metadata.create_all(libaccess.engine)


def recreate_all():
    import os

    assert os.getenv('ENV') in ['dev', 'staging'], 'must be dev or staging'
    Base.metadata.drop_all(libaccess.engine, checkfirst=True)
    Base.metadata.create_all(libaccess.engine, checkfirst=True)


def clear_db():
    for tbl in Base.metadata.tables:
        sql(
            libaccess.engine,
            f'''TRUNCATE TABLE {tbl};
ALTER TABLE {tbl} AUTO_INCREMENT = 1;''',
        )


Base = declarative_base()


class Model(Base):
    __abstract__ = True
    __bind_key__ = 'boilerplate'

    created_at = sa.Column(types.TIMESTAMP, server_default=text('CURRENT_TIMESTAMP'), nullable=False)
    updated_at = sa.Column(
        types.TIMESTAMP, server_default=text('CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP'), nullable=False
    )


TINYINT = mysql.TINYINT(unsigned=True)
SMALLINT = mysql.SMALLINT(unsigned=True)
MEDIUMINT = mysql.MEDIUMINT(unsigned=True)
INT = mysql.INTEGER(unsigned=True)
BIGINT = mysql.BIGINT(unsigned=True)
SINT = mysql.INTEGER(unsigned=False)
SBIGINT = mysql.BIGINT(unsigned=False)
CCY = sa.Numeric(13, 2)


class User(Model):
    __tablename__ = 'user'
    id_user = sa.Column(INT, primary_key=True)

    code = sa.Column(sa.String(100), nullable=False, unique=True)


class UserAccess(Model):
    __tablename__ = 'user_access'
    id_user_access = sa.Column(BIGINT, primary_key=True)

    id_user = sa.Column(INT, nullable=False, index=True)
    id_resource_role = sa.Column(INT, nullable=False, index=True)
    resource_ref = sa.Column(sa.String(50), nullable=False, index=True)  # cs_noon, darkstore_code,

    __table_args__ = (UniqueConstraint('id_user', 'id_resource_role', 'resource_ref', name='uq_user_access'),)


class ResourceRole(Model):
    __tablename__ = 'resource_role'
    id_resource_role = sa.Column(INT, primary_key=True)

    resource_type = sa.Column(sa.Enum(enums.ResourceType), nullable=False, index=True)
    role_type = sa.Column(sa.Enum(enums.RoleType), nullable=False, index=True)

    permissions = sa.Column(sa.JSON, nullable=False)
    name = sa.Column(sa.String(50), nullable=False)
    role_desc = sa.Column(sa.String(500), nullable=False, server_default='')

    __table_args__ = (UniqueConstraint('resource_type', 'role_type', name='uq_resource_role'),)
