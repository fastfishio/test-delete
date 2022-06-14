import os

from noonhelpers.v1 import auth_team

VAT_INVOICE_URL = auth_team.get_service_url('mp', 'mp-invoice-api')
MP_CODE = os.getenv('MP_CODE')  # make sure new MP code has been registered to `mp-invoice-api` service


def get_invoice_url_for(order_nr) -> str:
    return auth_team.auth_get(f'{VAT_INVOICE_URL}/{MP_CODE}/order/{order_nr}').json()['doc']  # return URL
