import logging
from typing import List, Dict

from boltons import iterutils
from noonhelpers.v1 import auth_team
from pydantic import BaseModel

MAX_ADDRESSES_FOR_BULK = 50
TEAM_CUSTOMER_URL = auth_team.get_service_url('mp', 'team-customer')
logger = logging.getLogger(__name__)


class CustomerAddress(BaseModel):
    first_name: str | None
    last_name: str | None
    phone: str | None
    street_address: str | None
    city_name_en: str | None
    country_code: str | None
    customer_code: str | None
    uphone_code: str | None
    is_phone_verified: bool | None
    email: str | None


def get_customer_address(address_key, fieldset=None) -> CustomerAddress:
    address_code, address_version = address_key.split('-')
    fieldset = f'?fieldset={fieldset}' if fieldset else ''
    response = auth_team.auth_get(f'{TEAM_CUSTOMER_URL}/customer-address/{address_code}/{address_version}{fieldset}')
    return CustomerAddress(**response.json())


def get_customer_info_bulk(address_key_list) -> List[Dict]:
    # Todo: Add an address_key version for this endpoint too (maybe post YFS)
    address_list = [{
        'address_code': address_key.split('-')[0],
        'address_version': address_key.split('-')[1]
    } for address_key in address_key_list]
    res = []
    for chunk in iterutils.chunked(address_list, MAX_ADDRESSES_FOR_BULK):
        res += auth_team.auth_post(f'{TEAM_CUSTOMER_URL}/customer-addresses', payload={"addresses": chunk}).json()
    return res


def customer_search_phone(phone_nr) -> List[str]:
    payload = {
        'phone': phone_nr
    }
    try:
        response = auth_team.auth_post(f'{TEAM_CUSTOMER_URL}/customer-search/phone', payload=payload).json()
        return [customer['customer_code'] for customer in response['customer_list']]
    except Exception as e:
        logger.error(f"customer.customer_search_phone:: unable to search customer by phone [customer service]: {e}")
        return []


def customer_search_email(email) -> List[str]:
    payload = {
        'email': email
    }
    try:
        response = auth_team.auth_post(f'{TEAM_CUSTOMER_URL}/customer-search/email', payload=payload).json()
        return [response['customer_code']]
    except Exception as e:
        logger.error(f"customer.customer_search_email:: unable to search customer by email [customer service]: {e}")
        return []
