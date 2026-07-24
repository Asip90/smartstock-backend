from unittest.mock import MagicMock, patch

from django.test import TestCase

from storefront.payouts import approve_and_send, get_pending_payout_requests, reject


class GetPendingPayoutRequestsTests(TestCase):
    @patch('storefront.payouts.fb.db')
    def test_liste_les_demandes_pending_avec_le_nom_de_la_boutique(self, mock_db):
        req_doc = MagicMock()
        req_doc.id = 'req1'
        req_doc.to_dict.return_value = {
            'shopId': 's1', 'amountRequested': 5000,
            'phoneNumber': '229010000', 'phoneCountry': 'BJ', 'status': 'pending',
        }
        shop_doc = MagicMock()
        shop_doc.exists = True
        shop_doc.to_dict.return_value = {'name': 'Ma Boutique', 'ownerId': 'u1'}

        def collection(name):
            m = MagicMock()
            if name == 'payoutRequests':
                m.where.return_value.stream.return_value = iter([req_doc])
            elif name == 'shops':
                m.document.return_value.get.return_value = shop_doc
            return m

        mock_db.return_value.collection.side_effect = collection

        results = get_pending_payout_requests()

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['id'], 'req1')
        self.assertEqual(results[0]['shopName'], 'Ma Boutique')
        self.assertEqual(results[0]['amountRequested'], 5000)


class ApproveAndSendTests(TestCase):
    @patch('storefront.payouts.fedapay.create_payout')
    @patch('storefront.payouts.fb.db')
    def test_appelle_fedapay_et_marque_sent(self, mock_db, mock_create_payout):
        req_doc = MagicMock()
        req_doc.exists = True
        req_doc.to_dict.return_value = {
            'shopId': 's1', 'amountRequested': 5000,
            'phoneNumber': '229010000', 'phoneCountry': 'BJ', 'status': 'pending',
        }
        shop_doc = MagicMock()
        shop_doc.exists = True
        shop_doc.to_dict.return_value = {'name': 'Ma Boutique', 'currency': 'XOF'}

        payout_requests_collection = MagicMock()
        payout_requests_collection.document.return_value.get.return_value = req_doc
        shops_collection = MagicMock()
        shops_collection.document.return_value.get.return_value = shop_doc

        def collection(name):
            return {'payoutRequests': payout_requests_collection, 'shops': shops_collection}[name]

        mock_db.return_value.collection.side_effect = collection
        mock_create_payout.return_value = {
            'fedapay_id': 'po_1', 'status': 'pending', 'fees': 75,
            'amount_debited': 5075, 'amount_transferred': 5000,
        }

        ok, message = approve_and_send('req1')

        self.assertTrue(ok)
        mock_create_payout.assert_called_once()
        self.assertEqual(mock_create_payout.call_args.kwargs['amount'], 5000)
        self.assertEqual(mock_create_payout.call_args.kwargs['phone_number'], '229010000')
        update_call = payout_requests_collection.document.return_value.update
        written = update_call.call_args[0][0]
        self.assertEqual(written['status'], 'sent')
        self.assertEqual(written['fedapayPayoutId'], 'po_1')
        self.assertEqual(written['feesAmount'], 75)
        self.assertEqual(written['amountSent'], 5000)
        self.assertEqual(written['totalDeducted'], 5075)

    @patch('storefront.payouts.fedapay.create_payout')
    @patch('storefront.payouts.fb.db')
    def test_refuse_si_deja_traitee(self, mock_db, mock_create_payout):
        req_doc = MagicMock()
        req_doc.exists = True
        req_doc.to_dict.return_value = {'shopId': 's1', 'status': 'sent'}
        mock_db.return_value.collection.return_value.document.return_value.get.return_value = req_doc

        ok, message = approve_and_send('req1')

        self.assertFalse(ok)
        mock_create_payout.assert_not_called()

    @patch('storefront.payouts.fedapay.create_payout', side_effect=Exception('boom'))
    @patch('storefront.payouts.fb.db')
    def test_echec_fedapay_marque_failed(self, mock_db, mock_create_payout):
        req_doc = MagicMock()
        req_doc.exists = True
        req_doc.to_dict.return_value = {
            'shopId': 's1', 'amountRequested': 5000,
            'phoneNumber': '229010000', 'phoneCountry': 'BJ', 'status': 'pending',
        }
        shop_doc = MagicMock()
        shop_doc.exists = True
        shop_doc.to_dict.return_value = {'name': 'Ma Boutique', 'currency': 'XOF'}

        payout_requests_collection = MagicMock()
        payout_requests_collection.document.return_value.get.return_value = req_doc
        shops_collection = MagicMock()
        shops_collection.document.return_value.get.return_value = shop_doc

        def collection(name):
            return {'payoutRequests': payout_requests_collection, 'shops': shops_collection}[name]

        mock_db.return_value.collection.side_effect = collection

        ok, message = approve_and_send('req1')

        self.assertFalse(ok)
        update_call = payout_requests_collection.document.return_value.update
        written = update_call.call_args[0][0]
        self.assertEqual(written['status'], 'failed')
        self.assertIn('boom', written['adminNote'])


class RejectTests(TestCase):
    @patch('storefront.payouts.fb.db')
    def test_marque_rejected_avec_la_note(self, mock_db):
        req_doc = MagicMock()
        req_doc.exists = True
        req_doc.to_dict.return_value = {'status': 'pending'}
        mock_db.return_value.collection.return_value.document.return_value.get.return_value = req_doc

        ok = reject('req1', 'numéro invalide')

        self.assertTrue(ok)
        update_call = mock_db.return_value.collection.return_value.document.return_value.update
        written = update_call.call_args[0][0]
        self.assertEqual(written['status'], 'rejected')
        self.assertEqual(written['adminNote'], 'numéro invalide')

    @patch('storefront.payouts.fb.db')
    def test_refuse_si_deja_traitee(self, mock_db):
        req_doc = MagicMock()
        req_doc.exists = True
        req_doc.to_dict.return_value = {'status': 'sent'}
        mock_db.return_value.collection.return_value.document.return_value.get.return_value = req_doc

        ok = reject('req1', 'trop tard')

        self.assertFalse(ok)
