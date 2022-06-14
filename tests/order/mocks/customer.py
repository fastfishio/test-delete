# todo: improve this mock to return the same kind of response that team-customer returns
from libexternal.customer import CustomerAddress

CUSTOMER_ADDRESS_MAP = {
    'A091': {
        '1': {
            'name': 'A091-1',
            'first_name': 'first',
            'last_name': 'last',
            'customer_code': "c1",
            'is_phone_verified': True,
            'city_name_en': 'Dubai',
            'city_name_ar': 'دبي',
            'area': 'Downtown',
            'phone': '+971980938',
            'lat': 252005240,
            'lng': 552807372,
            'street_address': 'Boulevard Plaza Tower 2, 7th Floor',
            'uphone_code': 'UC1975555555',
            'address_label': 'HOME',
            'address_key': 'A091-1',
            'email': 'example@domain.com'
        },
        '2': {
            'name': 'A091-2',
            'customer_code': "c1",
            'is_phone_verified': True,
            'lat': 252005240,
            'lng': 552807372,
            'city_name_en': 'Dubai',
            'city_name_ar': 'دبي',
            'area': 'Downtown',
            'phone': '+971980938',
            'street_address': 'Boulevard Plaza Tower 2, 7th Floor',
            'uphone_code': 'UC1975555555',
            'address_label': 'WORK',
            'address_key': 'A091-2'
        }
    },
    'A092': {
        '1': {
            'name': 'A092-1',
            'first_name': 'first',
            'last_name': 'last',
            'customer_code': "order_listing",
            'is_phone_verified': True,
            'city_name_en': 'Dubai',
            'city_name_ar': 'دبي',
            'area': 'Downtown',
            'phone': '+971980938',
            'lat': 252005240,
            'lng': 552807372,
            'street_address': 'Boulevard Plaza Tower 2, 7th Floor',
            'uphone_code': 'UC1975555555',
            'address_label': 'HOME',
            'address_key': 'A092-1',
            'email': 'example@domain.com'
        }
    }
}


def get_customer_address(address_key, fieldset=None) -> CustomerAddress:
    address_code, address_version = address_key.split('-')
    return CustomerAddress(**CUSTOMER_ADDRESS_MAP[address_code][address_version])


def customer_search_phone(phone_nr):
    res = []
    for address_code in CUSTOMER_ADDRESS_MAP.keys():
        for address_version in CUSTOMER_ADDRESS_MAP[address_code].keys():
            if CUSTOMER_ADDRESS_MAP[address_code][address_version]['phone'] == phone_nr:
                res.append(CUSTOMER_ADDRESS_MAP[address_code][address_version]['customer_code'])
    return res


def get_customer_info_bulk(address_key_list):
    address_list = [{
        'address_code': address_key.split('-')[0],
        'address_version': address_key.split('-')[1]
    } for address_key in address_key_list]
    res = []
    for address in address_list:
        res.append(CUSTOMER_ADDRESS_MAP[address['address_code']][address['address_version']])
    return res
