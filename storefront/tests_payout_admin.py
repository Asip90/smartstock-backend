from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase

User = get_user_model()


class PayoutAdminAccessTests(TestCase):
    def setUp(self):
        self.client = Client()

    def test_anonyme_redirige_vers_le_login(self):
        response = self.client.get('/admin/payouts/')
        self.assertEqual(response.status_code, 302)

    def test_utilisateur_non_staff_refuse(self):
        User.objects.create_user(username='u1', password='pass12345', is_staff=False)
        self.client.login(username='u1', password='pass12345')
        response = self.client.get('/admin/payouts/')
        self.assertEqual(response.status_code, 302)


class PayoutAdminStaffTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.staff = User.objects.create_user(
            username='admin1', password='pass12345', is_staff=True)
        self.client.login(username='admin1', password='pass12345')

    @patch('storefront.payout_admin.payouts.get_pending_payout_requests')
    def test_liste_les_demandes_en_attente(self, mock_list):
        mock_list.return_value = [
            {'id': 'req1', 'shopName': 'Ma Boutique', 'amountRequested': 5000,
             'phoneNumber': '229010000', 'phoneCountry': 'BJ'},
        ]
        response = self.client.get('/admin/payouts/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Ma Boutique')
        self.assertContains(response, '5000')

    @patch('storefront.payout_admin.payouts.approve_and_send')
    def test_approuver_appelle_approve_and_send(self, mock_approve):
        mock_approve.return_value = (True, 'ok')
        response = self.client.post('/admin/payouts/req1/approuver')
        mock_approve.assert_called_once_with('req1')
        self.assertRedirects(response, '/admin/payouts/', fetch_redirect_response=False)

    @patch('storefront.payout_admin.payouts.reject')
    def test_rejeter_appelle_reject_avec_la_note(self, mock_reject):
        mock_reject.return_value = True
        response = self.client.post('/admin/payouts/req1/rejeter', {'note': 'numéro invalide'})
        mock_reject.assert_called_once_with('req1', 'numéro invalide')
        self.assertRedirects(response, '/admin/payouts/', fetch_redirect_response=False)

    def test_approuver_refuse_en_get(self):
        response = self.client.get('/admin/payouts/req1/approuver')
        self.assertEqual(response.status_code, 405)
