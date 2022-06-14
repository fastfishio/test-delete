from jsql import sql

from liborder import engine
from liborder import domain


def get_order_details(order_nr):
    return sql(engine, '''
        SELECT * from sales_order where order_nr = :order_nr
    ''', order_nr=order_nr).dict()


def place_order(items, payment_method_code='cod', credit_amount=0, credit_card_mask=None, payment_token=None, delivery_preferences=None):
    session = domain.session.GetOrCreate().execute()
    assert not session.items, 'Session had items before calling the place order util'
    for item in items:
        domain.session.AddItem(sku=item[0], qty=item[1]).execute()
    session = domain.session.SetPaymentMethod(payment_method_code=payment_method_code, credit_amount=credit_amount,
                                              credit_card_mask=credit_card_mask, payment_token=payment_token).execute()
    if delivery_preferences:
        session = domain.session.SetDeliveryPreferences(delivery_preferences=delivery_preferences).execute()
    order_nr = domain.order.PlaceOrder(total=session.order_total).execute()['order_nr']
    return session, order_nr
