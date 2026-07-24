from unittest.mock import MagicMock, patch

from django.test import TestCase

from billing import fedapay


class CreatePayoutTests(TestCase):
    @patch('billing.fedapay.requests.post')
    def test_envoie_les_bons_champs_a_fedapay(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            'v1/payout': {
                'id': 'po_1', 'status': 'pending', 'amount': 5000,
                'fees': 75, 'amount_debited': 5075, 'amount_transferred': 5000,
            }
        }
        mock_post.return_value = mock_resp

        result = fedapay.create_payout(
            amount=5000, firstname='Awa', lastname='Traore',
            phone_number='229010000', phone_country='BJ', currency='XOF',
        )

        mock_resp.raise_for_status.assert_called_once()
        sent_json = mock_post.call_args.kwargs['json']
        self.assertEqual(sent_json['amount'], 5000)
        self.assertEqual(sent_json['currency'], {'iso': 'XOF'})
        self.assertEqual(sent_json['mode'], 'mobile_money')
        self.assertEqual(sent_json['customer']['firstname'], 'Awa')
        self.assertEqual(sent_json['customer']['lastname'], 'Traore')
        self.assertEqual(
            sent_json['customer']['phone_number'],
            {'number': '229010000', 'country': 'BJ'},
        )

        self.assertEqual(result['fedapay_id'], 'po_1')
        self.assertEqual(result['status'], 'pending')
        self.assertEqual(result['fees'], 75)
        self.assertEqual(result['amount_debited'], 5075)
        self.assertEqual(result['amount_transferred'], 5000)

    @patch('billing.fedapay.requests.post')
    def test_repli_sur_amount_transferred_si_amount_debited_absent(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            'payout': {'id': 'po_2', 'status': 'pending', 'amount': 5000},
        }
        mock_post.return_value = mock_resp

        result = fedapay.create_payout(
            amount=5000, firstname='Awa', lastname='Traore',
            phone_number='229010000', phone_country='BJ',
        )

        # Ni fees ni amount_debited renvoyés par FedaPay : on ne doit jamais
        # inventer un montant — repli sûr sur le montant demandé, fees=0.
        self.assertEqual(result['fees'], 0)
        self.assertEqual(result['amount_debited'], 5000)
        self.assertEqual(result['amount_transferred'], 5000)
