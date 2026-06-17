"""Tests de la tarification : essai 30 jours, -50% sur les 3 premiers mois d'un filleul."""
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase, override_settings

from billing.models import PromoCode, Referral, Transaction

UID = 'firebase-uid-abc'
EMAIL = 'filleul@example.com'
AUTH = {'HTTP_AUTHORIZATION': 'Bearer fake-token'}

FAKE_CHECKOUT = {'fedapay_id': 'x', 'url': 'http://t', 'token': 'tok'}


@override_settings(PRICE_MONTHLY=1900, PRICE_YEARLY=15000)
class PricingPromoTests(TestCase):
    def _patch_auth(self, uid=UID, email=EMAIL):
        p = patch('billing.firebase_service.verify_token', return_value=(uid, email))
        p.start()
        self.addCleanup(p.stop)

    def _patch_entitlement(self):
        # Pas d'entitlement existant par défaut + set_entitlement no-op (pas de Firestore).
        store = {}
        p_get = patch('billing.firebase_service.get_entitlement',
                      side_effect=lambda u: store.get(u))
        p_set = patch('billing.firebase_service.set_entitlement',
                      side_effect=lambda u, **kw: store.__setitem__(u, dict(kw, status=kw.get('status', 'free'))))
        p_get.start()
        p_set.start()
        self.addCleanup(p_get.stop)
        self.addCleanup(p_set.stop)
        return store

    def _make_promo(self, code='AWA2026'):
        return PromoCode.objects.create(code=code, influencer_name='Awa', trial_days=45)

    # --- signup ----------------------------------------------------------
    def test_signup_without_code_trial_30(self):
        self._patch_auth()
        self._patch_entitlement()
        resp = self.client.post('/api/signup', {}, content_type='application/json', **AUTH)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['trial_days'], 30)

    def test_signup_with_code_trial_30_and_referral_created(self):
        self._make_promo()
        self._patch_auth()
        self._patch_entitlement()
        resp = self.client.post('/api/signup', {'promo_code': 'awa2026'},
                                content_type='application/json', **AUTH)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['trial_days'], 30)
        self.assertTrue(Referral.objects.filter(referred_uid=UID).exists())

    def test_second_signup_with_code_conflicts(self):
        self._make_promo()
        self._patch_auth()
        self._patch_entitlement()
        first = self.client.post('/api/signup', {'promo_code': 'AWA2026'},
                                 content_type='application/json', **AUTH)
        self.assertEqual(first.status_code, 200)
        second = self.client.post('/api/signup', {'promo_code': 'AWA2026'},
                                  content_type='application/json', **AUTH)
        self.assertEqual(second.status_code, 409)

    # --- subscribe -------------------------------------------------------
    def _add_referral(self, months_left=3):
        code = self._make_promo()
        return Referral.objects.create(
            promo_code=code, referred_uid=UID, referred_email=EMAIL,
            discount_months_left=months_left)

    @patch('billing.fedapay.create_checkout', return_value=FAKE_CHECKOUT)
    def test_subscribe_referred_monthly_discounted(self, _m):
        self._add_referral()
        self._patch_auth()
        resp = self.client.post('/api/subscribe', {'plan': 'monthly'},
                                content_type='application/json', **AUTH)
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()['discounted'])
        tx = Transaction.objects.get(uid=UID)
        self.assertEqual(tx.amount, 950)
        self.assertTrue(tx.discounted)
        self.assertEqual(_m.call_args.kwargs['amount'], 950)

    @patch('billing.fedapay.create_checkout', return_value=FAKE_CHECKOUT)
    def test_subscribe_referred_yearly_discount_is_three_months_value(self, _m):
        # Annuel : réduction = 3 x (mensuel//2) = 2850 -> 15000-2850 = 12150.
        self._add_referral()
        self._patch_auth()
        resp = self.client.post('/api/subscribe', {'plan': 'yearly'},
                                content_type='application/json', **AUTH)
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()['discounted'])
        tx = Transaction.objects.get(uid=UID)
        self.assertEqual(tx.amount, 12150)
        self.assertEqual(_m.call_args.kwargs['amount'], 12150)

    @patch('billing.fedapay.create_checkout', return_value=FAKE_CHECKOUT)
    def test_subscribe_discount_persists_while_months_left(self, _m):
        # Même après un paiement, tant qu'il reste des mois, la remise tient.
        self._add_referral(months_left=2)
        Transaction.objects.create(uid=UID, email=EMAIL, plan='monthly',
                                   amount=950, status='paid', discounted=True)
        self._patch_auth()
        resp = self.client.post('/api/subscribe', {'plan': 'monthly'},
                                content_type='application/json', **AUTH)
        self.assertTrue(resp.json()['discounted'])
        self.assertEqual(_m.call_args.kwargs['amount'], 950)

    @patch('billing.fedapay.create_checkout', return_value=FAKE_CHECKOUT)
    def test_subscribe_full_price_when_discount_exhausted(self, _m):
        self._add_referral(months_left=0)
        self._patch_auth()
        resp = self.client.post('/api/subscribe', {'plan': 'monthly'},
                                content_type='application/json', **AUTH)
        self.assertFalse(resp.json()['discounted'])
        tx = Transaction.objects.get(uid=UID)
        self.assertEqual(tx.amount, 1900)
        self.assertEqual(_m.call_args.kwargs['amount'], 1900)

    @patch('billing.fedapay.create_checkout', return_value=FAKE_CHECKOUT)
    def test_subscribe_non_referred_full_price(self, _m):
        self._patch_auth()
        resp = self.client.post('/api/subscribe', {'plan': 'yearly'},
                                content_type='application/json', **AUTH)
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.json()['discounted'])
        tx = Transaction.objects.get(uid=UID)
        self.assertEqual(tx.amount, 15000)
        self.assertEqual(_m.call_args.kwargs['amount'], 15000)

    # --- apply-promo (ajout d'un code depuis la page d'abonnement) --------
    def test_apply_promo_creates_referral_and_returns_discount(self):
        self._make_promo()
        self._patch_auth()
        resp = self.client.post('/api/apply-promo', {'promo_code': 'awa2026'},
                                content_type='application/json', **AUTH)
        self.assertEqual(resp.status_code, 200)
        promo = resp.json()['promo']
        self.assertTrue(promo['referred'])
        self.assertFalse(promo['can_apply_promo'])
        self.assertEqual(promo['discount_months_left'], 3)
        self.assertEqual(promo['prices']['monthly']['final'], 950)
        self.assertTrue(Referral.objects.filter(referred_uid=UID).exists())

    def test_apply_promo_conflict_if_already_referred(self):
        self._add_referral()
        self._patch_auth()
        resp = self.client.post('/api/apply-promo', {'promo_code': 'AWA2026'},
                                content_type='application/json', **AUTH)
        self.assertEqual(resp.status_code, 409)

    def test_apply_promo_invalid_code(self):
        self._patch_auth()
        resp = self.client.post('/api/apply-promo', {'promo_code': 'NOPE'},
                                content_type='application/json', **AUTH)
        self.assertEqual(resp.status_code, 400)

    def test_me_exposes_promo_state_for_non_referred(self):
        self._patch_auth()
        self._patch_entitlement()
        resp = self.client.get('/api/me', **AUTH)
        promo = resp.json()['promo']
        self.assertFalse(promo['referred'])
        self.assertTrue(promo['can_apply_promo'])
        self.assertFalse(promo['prices']['monthly']['discounted'])

    # --- webhook : décompte des mois remisés ------------------------------
    @patch('billing.fedapay.verify_webhook_signature', return_value=True)
    def test_webhook_paid_monthly_decrements_discount_months(self, _sig):
        self._patch_entitlement()
        ref = self._add_referral(months_left=3)
        tx = Transaction.objects.create(uid=UID, email=EMAIL, plan='monthly',
                                        amount=950, discounted=True, fedapay_id='fp1')
        event = {'entity': {'id': 'fp1', 'status': 'approved'}}
        resp = self.client.post('/api/webhook/fedapay', event,
                                content_type='application/json')
        self.assertEqual(resp.status_code, 200)
        ref.refresh_from_db()
        self.assertEqual(ref.discount_months_left, 2)

    @patch('billing.fedapay.verify_webhook_signature', return_value=True)
    def test_webhook_paid_yearly_zeroes_discount_months(self, _sig):
        self._patch_entitlement()
        ref = self._add_referral(months_left=3)
        Transaction.objects.create(uid=UID, email=EMAIL, plan='yearly',
                                   amount=12150, discounted=True, fedapay_id='fp2')
        event = {'entity': {'id': 'fp2', 'status': 'approved'}}
        self.client.post('/api/webhook/fedapay', event,
                         content_type='application/json')
        ref.refresh_from_db()
        self.assertEqual(ref.discount_months_left, 0)


class BackfillEntitlementsTests(TestCase):
    """Grand-fathering : un entitlement pour chaque UID connu sans doc."""

    def setUp(self):
        # UID-1 a déjà un doc, UID-2 et UID-3 (parrainage) n'en ont pas.
        Transaction.objects.create(uid='uid-1', email='a@x', plan='monthly',
                                   amount=1900, status='paid')
        Transaction.objects.create(uid='uid-2', email='b@x', plan='monthly',
                                   amount=1900, status='paid')
        code = PromoCode.objects.create(code='REF', influencer_name='X', trial_days=14)
        Referral.objects.create(promo_code=code, referred_uid='uid-3',
                                referred_email='c@x')
        # uid-1 possède déjà un entitlement, les autres non.
        self._existing = {'uid-1': {'plan': 'pro', 'status': 'active'}}

    def _patch_fb(self, auth_uids=()):
        p_get = patch('billing.firebase_service.get_entitlement',
                      side_effect=lambda u: self._existing.get(u))
        p_set = patch('billing.firebase_service.set_entitlement')
        p_list = patch('billing.firebase_service.list_all_uids',
                       return_value=list(auth_uids))
        get = p_get.start()
        set_ = p_set.start()
        p_list.start()
        self.addCleanup(p_get.stop)
        self.addCleanup(p_set.stop)
        self.addCleanup(p_list.stop)
        return get, set_

    def test_dry_run_never_writes(self):
        _get, set_ = self._patch_fb()
        out = StringIO()
        call_command('backfill_entitlements', stdout=out)
        set_.assert_not_called()
        self.assertIn('dry-run', out.getvalue())

    def test_commit_writes_only_missing(self):
        _get, set_ = self._patch_fb()
        out = StringIO()
        call_command('backfill_entitlements', '--commit', stdout=out)
        # Écrit uniquement pour uid-2 et uid-3 (uid-1 a déjà un doc).
        written = {call.args[0] for call in set_.call_args_list}
        self.assertEqual(written, {'uid-2', 'uid-3'})
        self.assertNotIn('uid-1', written)
        # Vérifie les kwargs passés à set_entitlement.
        kwargs = set_.call_args_list[0].kwargs
        self.assertEqual(kwargs['plan'], 'pro')
        self.assertEqual(kwargs['status'], 'active')
        self.assertIn('current_period_end', kwargs)

    def test_commit_includes_firebase_auth_only_users(self):
        # uid-4 n'existe qu'au niveau Firebase Auth (jamais vu en base) et n'a pas de doc.
        _get, set_ = self._patch_fb(auth_uids=['uid-1', 'uid-4'])
        out = StringIO()
        call_command('backfill_entitlements', '--commit', stdout=out)
        written = {call.args[0] for call in set_.call_args_list}
        self.assertEqual(written, {'uid-2', 'uid-3', 'uid-4'})
