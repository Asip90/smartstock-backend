"""Tests de l'API JSON de l'espace promoteur (auth Firebase Bearer)."""
from unittest.mock import patch

from django.test import TestCase
from django.contrib.auth.models import User

from billing.models import (
    PromoCode, Referral, Transaction, Commission, WithdrawalRequest,
)

UID = 'firebase-uid-123'
EMAIL = 'promo@example.com'
AUTH = {'HTTP_AUTHORIZATION': 'Bearer fake-token'}


class PromoterApiTests(TestCase):
    def _patch_auth(self, uid=UID, email=EMAIL):
        p = patch('billing.firebase_service.verify_token', return_value=(uid, email))
        p.start()
        self.addCleanup(p.stop)

    # --- auth ------------------------------------------------------------
    def test_requires_token(self):
        for url in ('/api/promoter/me', '/api/promoter/dashboard'):
            resp = self.client.get(url)
            self.assertEqual(resp.status_code, 401, url)
        resp = self.client.post('/api/promoter/code', {}, content_type='application/json')
        self.assertEqual(resp.status_code, 401)
        resp = self.client.post('/api/promoter/withdraw', {}, content_type='application/json')
        self.assertEqual(resp.status_code, 401)

    # --- create code -----------------------------------------------------
    def test_create_valid_code(self):
        self._patch_auth()
        resp = self.client.post('/api/promoter/code', {'code': 'awa2026'},
                                content_type='application/json', **AUTH)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), {'code': 'AWA2026'})
        pc = PromoCode.objects.get(code='AWA2026')
        self.assertEqual(pc.commission_pct, 25)
        self.assertEqual(pc.firebase_uid, UID)
        self.assertEqual(pc.influencer_name, EMAIL)
        self.assertEqual(pc.owner.username, EMAIL)

    def test_create_invalid_regex(self):
        self._patch_auth()
        resp = self.client.post('/api/promoter/code', {'code': 'AB'},
                                content_type='application/json', **AUTH)
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(PromoCode.objects.filter(code='AB').exists())

    def test_create_duplicate_code(self):
        PromoCode.objects.create(code='AWA2026', influencer_name='someone')
        self._patch_auth()
        resp = self.client.post('/api/promoter/code', {'code': 'awa2026'},
                                content_type='application/json', **AUTH)
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(PromoCode.objects.filter(code='AWA2026').count(), 1)

    def test_second_code_for_same_user_conflicts(self):
        self._patch_auth()
        first = self.client.post('/api/promoter/code', {'code': 'AWA2026'},
                                 content_type='application/json', **AUTH)
        self.assertEqual(first.status_code, 200)
        resp = self.client.post('/api/promoter/code', {'code': 'BOB2026'},
                                content_type='application/json', **AUTH)
        self.assertEqual(resp.status_code, 409)
        self.assertFalse(PromoCode.objects.filter(code='BOB2026').exists())

    # --- me --------------------------------------------------------------
    def test_me_reflects_promoter_status(self):
        self._patch_auth()
        resp = self.client.get('/api/promoter/me', **AUTH)
        self.assertEqual(resp.json(),
                         {'is_promoter': False, 'code': None, 'commission_pct': None})
        self.client.post('/api/promoter/code', {'code': 'AWA2026'},
                         content_type='application/json', **AUTH)
        resp = self.client.get('/api/promoter/me', **AUTH)
        self.assertEqual(resp.json(),
                         {'is_promoter': True, 'code': 'AWA2026', 'commission_pct': 25})

    # --- dashboard -------------------------------------------------------
    def test_dashboard_not_promoter(self):
        self._patch_auth()
        resp = self.client.get('/api/promoter/dashboard', **AUTH)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), {'is_promoter': False})

    def test_dashboard_reflects_balance_and_referrals(self):
        user = User.objects.create_user(username=EMAIL, email=EMAIL)
        code = PromoCode.objects.create(owner=user, code='AWA2026',
                                        influencer_name=EMAIL, firebase_uid=UID)
        # Deux filleuls, un paiement -> une commission de 2500.
        ref = Referral.objects.create(promo_code=code, referred_uid='f1',
                                      referred_email='f1@x.com')
        Referral.objects.create(promo_code=code, referred_uid='f2',
                                referred_email='f2@x.com')
        tx = Transaction.objects.create(uid='f1', email='f1@x.com',
                                        plan='monthly', amount=10000, status='paid')
        Commission.objects.create(referral=ref, transaction=tx, amount=2500)

        self._patch_auth()
        resp = self.client.get('/api/promoter/dashboard', **AUTH)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['code'], 'AWA2026')
        self.assertEqual(data['referrals_count'], 2)
        self.assertEqual(data['balance']['earned'], 2500)
        self.assertEqual(data['balance']['available'], 2500)

    # --- withdraw --------------------------------------------------------
    def _setup_balance(self, earned=5000):
        user = User.objects.create_user(username=EMAIL, email=EMAIL)
        code = PromoCode.objects.create(owner=user, code='AWA2026',
                                        influencer_name=EMAIL, firebase_uid=UID)
        ref = Referral.objects.create(promo_code=code, referred_uid='f1',
                                      referred_email='f1@x.com')
        tx = Transaction.objects.create(uid='f1', email='f1@x.com',
                                        plan='monthly', amount=earned * 4, status='paid')
        Commission.objects.create(referral=ref, transaction=tx, amount=earned)
        return user

    def test_withdraw_over_available(self):
        self._setup_balance(earned=5000)
        self._patch_auth()
        resp = self.client.post('/api/promoter/withdraw',
                                {'amount': 6000, 'contact': '0600'},
                                content_type='application/json', **AUTH)
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(WithdrawalRequest.objects.exists())

    def test_valid_withdraw_creates_pending(self):
        user = self._setup_balance(earned=5000)
        self._patch_auth()
        resp = self.client.post('/api/promoter/withdraw',
                                {'amount': 3000, 'contact': '0600'},
                                content_type='application/json', **AUTH)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), {'ok': True})
        wr = WithdrawalRequest.objects.get(owner=user)
        self.assertEqual(wr.amount, 3000)
        self.assertEqual(wr.contact, '0600')
        self.assertEqual(wr.status, 'pending')
