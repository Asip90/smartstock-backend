from django.test import TestCase
from django.contrib.auth.models import User
from billing.models import PromoCode


class PromoterSignupTests(TestCase):
    def test_signup_creates_user_and_redirects_to_welcome(self):
        resp = self.client.post('/promoteur/inscription', {
            'full_name': 'Awa Diop', 'email': 'awa@example.com',
            'password': 'secret123', 'password2': 'secret123',
        })
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, '/promoteur/bienvenue')
        self.assertTrue(User.objects.filter(username='awa@example.com').exists())

    def test_signup_rejects_duplicate_email(self):
        User.objects.create_user('awa@example.com', 'awa@example.com', 'x')
        resp = self.client.post('/promoteur/inscription', {
            'full_name': 'Awa', 'email': 'awa@example.com',
            'password': 'secret123', 'password2': 'secret123',
        })
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'déjà')

    def test_create_code_available(self):
        User.objects.create_user('awa@example.com', 'awa@example.com', 'secret123')
        self.client.login(username='awa@example.com', password='secret123')
        resp = self.client.post('/promoteur/code', {'code': 'AWA2026'})
        self.assertEqual(resp.status_code, 200)
        pc = PromoCode.objects.get(code='AWA2026')
        self.assertEqual(pc.commission_pct, 25)
        self.assertContains(resp, 'AWA2026')

    def test_create_code_taken(self):
        PromoCode.objects.create(code='AWA2026', influencer_name='x')
        User.objects.create_user('awa@example.com', 'awa@example.com', 'secret123')
        self.client.login(username='awa@example.com', password='secret123')
        resp = self.client.post('/promoteur/code', {'code': 'awa2026'})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'pris')
        self.assertEqual(PromoCode.objects.filter(code='AWA2026').count(), 1)

    def test_create_code_length_validation(self):
        User.objects.create_user('awa@example.com', 'awa@example.com', 'secret123')
        self.client.login(username='awa@example.com', password='secret123')
        resp = self.client.post('/promoteur/code', {'code': 'AB'})
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(PromoCode.objects.filter(code='AB').exists())

    def test_welcome_redirects_to_dashboard_if_code_exists(self):
        user = User.objects.create_user('awa@example.com', 'awa@example.com', 'secret123')
        PromoCode.objects.create(owner=user, code='AWA2026', influencer_name='Awa')
        self.client.login(username='awa@example.com', password='secret123')
        resp = self.client.get('/promoteur/bienvenue')
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, '/promoteur/')
