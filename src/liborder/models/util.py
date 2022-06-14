from jsql import sql
from noonutil.v1 import miscutil
from noonutil.v2 import sqlutil
from liborder.context import ctx

from liborder import engine


@miscutil.cached()
def get_code_by_id(table, id):
    code = sql(engine, 'SELECT code FROM {{table}} WHERE id_{{table}}=:id', table=table, id=id).scalar()
    assert code, f'unknown {table} "{id}"'
    return code


@miscutil.cached()
def get_id_by_code(table, code):
    id = sql(engine, 'SELECT id_{{table}} FROM {{table}} WHERE code=:code', table=table, code=code).scalar()
    assert id, f'unknown {table} "{code}"'
    return id


def validate_order_nr(order_nr: str):
    sqlutil.assert_scalar(
        1, 'Order not found', ctx.conn, "SELECT 1 FROM sales_order WHERE order_nr = :order_nr", order_nr=order_nr
    )


def validate_cs_order_comment_code(comment_code: str):
    sqlutil.assert_scalar(
        1,
        'Comment not found',
        ctx.conn,
        "SELECT 1 FROM cs_order_comment WHERE comment_code=:comment_code",
        comment_code=comment_code,
    )
