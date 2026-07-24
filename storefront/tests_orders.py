from unittest.mock import MagicMock, patch

from django.test import TestCase

from storefront.orders import CartLineError, build_order_lines, create_order


class BuildOrderLinesTests(TestCase):
    @patch('storefront.orders.fb_read.get_public_products_by_ids')
    def test_construit_les_lignes_avec_prix_et_nom_reels(self, mock_get):
        mock_get.return_value = {
            'p1': {'id': 'p1', 'name': 'Sac', 'price': 1000, 'inStock': True, 'stockQty': 5},
        }
        lines = build_order_lines('s1', {'p1': 2})
        self.assertEqual(lines, [{'productId': 'p1', 'name': 'Sac', 'price': 1000, 'qty': 2}])

    @patch('storefront.orders.fb_read.get_public_products_by_ids')
    def test_leve_cart_line_error_si_produit_absent(self, mock_get):
        mock_get.return_value = {}
        with self.assertRaises(CartLineError) as ctx:
            build_order_lines('s1', {'p1': 1})
        self.assertEqual(ctx.exception.product_id, 'p1')
        self.assertEqual(ctx.exception.reason, 'unavailable')

    @patch('storefront.orders.fb_read.get_public_products_by_ids')
    def test_leve_cart_line_error_si_stock_insuffisant(self, mock_get):
        mock_get.return_value = {
            'p1': {'id': 'p1', 'name': 'Sac', 'price': 1000, 'inStock': True, 'stockQty': 1},
        }
        with self.assertRaises(CartLineError) as ctx:
            build_order_lines('s1', {'p1': 5})
        self.assertEqual(ctx.exception.reason, 'insufficient_stock')
        self.assertEqual(ctx.exception.available, 1)

    @patch('storefront.orders.fb_read.get_public_products_by_ids')
    def test_leve_cart_line_error_si_hors_stock(self, mock_get):
        mock_get.return_value = {
            'p1': {'id': 'p1', 'name': 'Sac', 'price': 1000, 'inStock': False, 'stockQty': 0},
        }
        with self.assertRaises(CartLineError) as ctx:
            build_order_lines('s1', {'p1': 1})
        self.assertEqual(ctx.exception.reason, 'insufficient_stock')
        self.assertEqual(ctx.exception.available, 0)


class CreateOrderTests(TestCase):
    @patch('storefront.orders.fb.db')
    def test_ecrit_le_document_storeOrders_avec_les_bons_champs(self, mock_db):
        mock_add = mock_db.return_value.collection.return_value.add
        mock_doc_ref = MagicMock()
        mock_doc_ref.id = 'order123'
        mock_add.return_value = (None, mock_doc_ref)

        order_id = create_order(
            's1',
            customer_name='Awa',
            customer_phone='2290100000000',
            customer_address='Cotonou',
            lines=[{'productId': 'p1', 'name': 'Sac', 'price': 1000, 'qty': 2}],
        )

        self.assertEqual(order_id, 'order123')
        written = mock_add.call_args[0][0]
        self.assertEqual(written['shopId'], 's1')
        self.assertEqual(written['status'], 'pending')
        self.assertEqual(written['paymentMode'], 'cash_on_delivery')
        self.assertIsNone(written['paymentRef'])
        self.assertEqual(written['totalAmount'], 2000)
        self.assertEqual(written['customerName'], 'Awa')
        self.assertEqual(written['items'][0]['productId'], 'p1')
