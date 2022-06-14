# import json
#
# from jsql import sql
#
# from libindexing.importers.price import BoilerplatePriceImport
# from libutil import pubsub
# from libutil.util import get_engine
#
#
# def get_price_for(sku, wh_code):
#     return sql(get_engine('boilerplate_offer'), '''SELECT offer_price FROM offer WHERE sku = :sku AND wh_code = :wh_code''',
#                wh_code=wh_code, sku=sku).scalar()
#
#
# def test_simple_invalid_psku(monkeypatch, data_indexing, data_noon_patalog):
#     def init_mock(self):
#         self.rows = [{
#             'country_code': 'AE',
#             'warehouse_code': 'WH2',
#             'id_partner': 1,
#             'partner_sku': 'PSKU1000',
#             'offer_price': 15
#         }]
#         self.params = {'code': 'I1', 'id_partner': 1}
#
#     def afterexecute_mock(self):
#         pass
#
#     def mock_publisher(message):
#         assert False, "This should not be called"
#
#     def mock_get_publisher(topic, project=None):
#         return mock_publisher
#
#     monkeypatch.setattr(BoilerplatePriceImport, '__init__', init_mock)
#     monkeypatch.setattr(BoilerplatePriceImport, 'afterexecute', afterexecute_mock)
#     monkeypatch.setattr(pubsub, 'get_publisher', mock_get_publisher)
#     importer = BoilerplatePriceImport()
#     importer.process()
#     assert len(importer.errors) == 1, "Row should fail for invalid psku"
#
#
# def test_simple_valid_psku(monkeypatch, data_indexing, data_noon_patalog):
#     def init_mock(self):
#         self.rows = [{
#             'country_code': 'AE',
#             'warehouse_code': 'WH2',
#             'id_partner': 1,
#             'partner_sku': 'PSKU-1',
#             'offer_price': 15
#         }]
#         self.params = {'code': 'I1', 'id_partner': 1}
#
#     def afterexecute_mock(self):
#         pass
#
#     def mock_publisher(message):
#         message = json.loads(message)
#         assert message == [{'sku': 'Z0001', 'wh_code': 'WH2'}], "Incorrect message"
#
#     def mock_get_publisher(topic, project=None):
#         return mock_publisher
#
#     monkeypatch.setattr(BoilerplatePriceImport, '__init__', init_mock)
#     monkeypatch.setattr(BoilerplatePriceImport, 'afterexecute', afterexecute_mock)
#     monkeypatch.setattr(pubsub, 'get_publisher', mock_get_publisher)
#     importer = BoilerplatePriceImport()
#     importer.process()
#     assert len(importer.errors) == 0, "Row should pass"
#     assert get_price_for('Z0001', 'WH2') == 15, "Incorrect price or not updated"
