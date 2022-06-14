from jsql import sql

from liborder import engine


def get_order_details(order_nr):
    return sql(engine, '''
        SELECT * from sales_order where order_nr = :order_nr
    ''', order_nr=order_nr).dict()
