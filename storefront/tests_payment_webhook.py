from unittest.mock import patch

from django.test import Client, TestCase


class StorefrontFedapayWebhookTests(TestCase):
    def setUp(self):
        self.client = Client()

    def test_refuse_si_signature_invalide(self):
        with patch('storefront.payment_webhook.fedapay.verify_webhook_signature', return_value=False):
            response = self.client.post(
                '/api/webhook/fedapay/storefront', data=b'{}',
                content_type='application/json',
            )
        self.assertEqual(response.status_code, 400)

    @patch('storefront.payment_webhook.orders.mark_order_paid')
    @patch('storefront.payment_webhook.fedapay.verify_webhook_signature', return_value=True)
    def test_statut_paye_appelle_mark_order_paid(self, mock_verify, mock_mark):
        payload = b'{"entity": {"id": "fp_tx_1", "status": "approved"}}'
        response = self.client.post(
            '/api/webhook/fedapay/storefront', data=payload,
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        mock_mark.assert_called_once_with('fp_tx_1')

    @patch('storefront.payment_webhook.orders.mark_order_paid')
    @patch('storefront.payment_webhook.fedapay.verify_webhook_signature', return_value=True)
    def test_statut_non_paye_nappelle_pas_mark_order_paid(self, mock_verify, mock_mark):
        payload = b'{"entity": {"id": "fp_tx_1", "status": "pending"}}'
        response = self.client.post(
            '/api/webhook/fedapay/storefront', data=payload,
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        mock_mark.assert_not_called()

    def test_refuse_si_get(self):
        response = self.client.get('/api/webhook/fedapay/storefront')
        self.assertEqual(response.status_code, 400)
