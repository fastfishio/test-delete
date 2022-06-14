from liborder.domain import boilerplate_event
from libexternal import customer
from tests.order.mocks import event as mocked_event
from tests.order.mocks import customer as mocked_customer

customer.get_customer_address = mocked_customer.get_customer_address
customer.customer_search_phone = mocked_customer.customer_search_phone
customer.get_customer_info_bulk = mocked_customer.get_customer_info_bulk
boilerplate_event.get_events = mocked_event.mock_get_events
