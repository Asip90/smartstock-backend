import hashlib
import hmac

from django.test import TestCase, override_settings

from billing import fedapay


class VerifyWebhookSignatureSecretTests(TestCase):
    @override_settings(FEDAPAY_WEBHOOK_SECRET='secret-abonnement')
    def test_repli_sur_fedapay_webhook_secret_si_secret_non_fourni(self):
        payload = b'{"entity": {"id": "1"}}'
        signature = hmac.new(b'secret-abonnement', payload, hashlib.sha256).hexdigest()
        self.assertTrue(fedapay.verify_webhook_signature(payload, signature))

    def test_utilise_le_secret_fourni_explicitement(self):
        payload = b'{"entity": {"id": "1"}}'
        signature = hmac.new(b'secret-boutique', payload, hashlib.sha256).hexdigest()
        self.assertTrue(
            fedapay.verify_webhook_signature(payload, signature, secret='secret-boutique'))

    @override_settings(FEDAPAY_WEBHOOK_SECRET='secret-abonnement')
    def test_secret_boutique_ne_valide_pas_avec_le_secret_abonnement(self):
        payload = b'{"entity": {"id": "1"}}'
        signature = hmac.new(b'secret-abonnement', payload, hashlib.sha256).hexdigest()
        self.assertFalse(
            fedapay.verify_webhook_signature(payload, signature, secret='secret-boutique'))
