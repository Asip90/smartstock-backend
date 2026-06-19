"""Tests de la fiabilisation de la confirmation de paiement :
- `_apply_paid_transaction` (logique partagée, idempotente, commission, remise) ;
- endpoint `/api/confirm` (vérification FedaPay) ;
- commande `reconcile_fedapay` (rattrapage idempotent).
"""
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase

from billing.models import PromoCode, Referral, Transaction, Commission
from billing.views import _apply_paid_transaction

UID = 'firebase-uid-filleul'
EMAIL = 'filleul@example.com'
AUTH = {'HTTP_AUTHORIZATION': 'Bearer fake-token'}


class PaymentConfirmTests(TestCase):
    def _patch_auth(self, uid=UID, email=EMAIL):
        p = patch('billing.firebase_service.verify_token', return_value=(uid, email))
        p.start()
        self.addCleanup(p.stop)

    def _patch_entitlement(self):
        store = {}
        p_get = patch('billing.firebase_service.get_entitlement',
                      side_effect=lambda u: store.get(u))
        p_set = patch('billing.firebase_service.set_entitlement',
                      side_effect=lambda u, **kw: store.__setitem__(u, dict(kw)))
        p_get.start()
        p_set.start()
        self.addCleanup(p_get.stop)
        self.addCleanup(p_set.stop)
        return store

    def _referred_tx(self, *, amount=950, discounted=True, plan='monthly', pct=25):
        owner = User.objects.create_user(username='promo@example.com',
                                         email='promo@example.com')
        code = PromoCode.objects.create(
            code='NOVA123', influencer_name='Nova', owner=owner, commission_pct=pct)
        ref = Referral.objects.create(
            promo_code=code, referred_uid=UID, referred_email=EMAIL,
            discount_months_left=3)
        tx = Transaction.objects.create(
            uid=UID, email=EMAIL, plan=plan, amount=amount,
            discounted=discounted, fedapay_id='111519400', status='pending')
        return code, ref, tx

    # --- _apply_paid_transaction ----------------------------------------
    def test_apply_creates_commission_and_decrements_discount(self):
        self._patch_entitlement()
        _, ref, tx = self._referred_tx(amount=950, pct=25)
        changed = _apply_paid_transaction(tx)
        self.assertTrue(changed)
        tx.refresh_from_db()
        ref.refresh_from_db()
        self.assertEqual(tx.status, 'paid')
        self.assertIsNotNone(tx.paid_at)
        com = Commission.objects.get(transaction=tx)
        self.assertEqual(com.amount, 950 * 25 // 100)  # 237
        self.assertEqual(ref.discount_months_left, 2)  # mensuel remisé -> -1

    def test_apply_is_idempotent(self):
        self._patch_entitlement()
        _, ref, tx = self._referred_tx()
        self.assertTrue(_apply_paid_transaction(tx))
        self.assertFalse(_apply_paid_transaction(tx))  # déjà payée
        self.assertEqual(Commission.objects.filter(transaction=tx).count(), 1)
        ref.refresh_from_db()
        self.assertEqual(ref.discount_months_left, 2)  # pas décrémenté deux fois

    # --- /api/confirm ----------------------------------------------------
    def test_confirm_requires_auth(self):
        resp = self.client.post('/api/confirm', {}, content_type='application/json')
        self.assertEqual(resp.status_code, 401)

    def test_confirm_unknown_transaction(self):
        self._patch_auth()
        resp = self.client.post('/api/confirm', {'transaction_id': 999},
                                content_type='application/json', **AUTH)
        self.assertEqual(resp.status_code, 404)

    @patch('billing.fedapay.get_transaction_status', return_value='approved')
    def test_confirm_approved_transaction(self, _m):
        self._patch_auth()
        self._patch_entitlement()
        _, _ref, tx = self._referred_tx()
        resp = self.client.post('/api/confirm', {'transaction_id': tx.id},
                                content_type='application/json', **AUTH)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['status'], 'paid')
        tx.refresh_from_db()
        self.assertEqual(tx.status, 'paid')
        self.assertTrue(Commission.objects.filter(transaction=tx).exists())

    @patch('billing.fedapay.get_transaction_status', return_value='pending')
    def test_confirm_not_yet_paid_stays_pending(self, _m):
        self._patch_auth()
        self._patch_entitlement()
        _, _ref, tx = self._referred_tx()
        resp = self.client.post('/api/confirm', {'transaction_id': tx.id},
                                content_type='application/json', **AUTH)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['status'], 'pending')
        self.assertFalse(Commission.objects.filter(transaction=tx).exists())

    @patch('billing.fedapay.get_transaction_status', return_value='approved')
    def test_confirm_scoped_to_authenticated_uid(self, _m):
        # Une transaction d'un autre uid ne doit pas être confirmable.
        self._patch_auth(uid='someone-else')
        self._patch_entitlement()
        _, _ref, tx = self._referred_tx()  # tx.uid = UID, pas 'someone-else'
        resp = self.client.post('/api/confirm', {'transaction_id': tx.id},
                                content_type='application/json', **AUTH)
        self.assertEqual(resp.status_code, 404)

    # --- reconcile_fedapay ----------------------------------------------
    @patch('billing.fedapay.get_transaction_status', return_value='approved')
    def test_reconcile_dry_run_does_not_write(self, _m):
        self._patch_entitlement()
        _, _ref, tx = self._referred_tx()
        call_command('reconcile_fedapay')  # sans --commit
        tx.refresh_from_db()
        self.assertEqual(tx.status, 'pending')
        self.assertFalse(Commission.objects.exists())

    # --- garde-fou auto-parrainage --------------------------------------
    def test_apply_promo_rejects_self_referral(self):
        self._patch_auth(uid=UID, email=EMAIL)
        self._patch_entitlement()
        # Code dont le promoteur EST l'utilisateur courant (firebase_uid == UID).
        PromoCode.objects.create(
            code='SELF123', influencer_name='Moi', firebase_uid=UID)
        resp = self.client.post('/api/apply-promo', {'promo_code': 'SELF123'},
                                content_type='application/json', **AUTH)
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.json()['error'], 'auto_parrainage_interdit')
        self.assertFalse(Referral.objects.filter(referred_uid=UID).exists())

    @patch('billing.fedapay.get_transaction_status', return_value='approved')
    def test_no_commission_on_self_referral(self, _m):
        self._patch_auth()
        self._patch_entitlement()
        # Parrainage où le filleul est aussi le promoteur (firebase_uid == UID).
        code = PromoCode.objects.create(
            code='SELF123', influencer_name='Moi', firebase_uid=UID,
            commission_pct=25)
        Referral.objects.create(
            promo_code=code, referred_uid=UID, referred_email=EMAIL)
        tx = Transaction.objects.create(
            uid=UID, email=EMAIL, plan='monthly', amount=950, discounted=True,
            fedapay_id='999', status='pending')
        resp = self.client.post('/api/confirm', {'transaction_id': tx.id},
                                content_type='application/json', **AUTH)
        self.assertEqual(resp.status_code, 200)
        tx.refresh_from_db()
        self.assertEqual(tx.status, 'paid')  # abonnement bien activé
        self.assertFalse(Commission.objects.exists())  # mais pas de commission

    @patch('billing.fedapay.get_transaction_status', return_value='approved')
    def test_reconcile_commit_confirms(self, _m):
        self._patch_entitlement()
        _, _ref, tx = self._referred_tx()
        call_command('reconcile_fedapay', '--commit')
        tx.refresh_from_db()
        self.assertEqual(tx.status, 'paid')
        self.assertEqual(Commission.objects.filter(transaction=tx).count(), 1)
        # Idempotent : un second passage ne crée pas de doublon.
        call_command('reconcile_fedapay', '--commit')
        self.assertEqual(Commission.objects.filter(transaction=tx).count(), 1)
