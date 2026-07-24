"""Client minimal FedaPay (API REST) — création de transaction + token de paiement.

Docs : https://docs.fedapay.com . On n'utilise QUE la clé secrète, côté serveur.
"""
import hmac
import hashlib

import requests
from django.conf import settings


def _base_url():
    return ('https://sandbox-api.fedapay.com'
            if settings.FEDAPAY_ENV != 'live'
            else 'https://api.fedapay.com')


def _headers():
    return {
        'Authorization': f'Bearer {settings.FEDAPAY_SECRET_KEY}',
        'Content-Type': 'application/json',
    }


def create_checkout(*, amount: int, description: str, customer_email: str,
                    callback_url: str = '', currency: str = 'XOF'):
    """Crée une transaction FedaPay puis un token de paiement.

    `currency` : XOF par défaut (abonnements Pro) ; la boutique en ligne
    passe la devise de la boutique (`ShopModel.currency`).

    Retourne {'fedapay_id', 'token', 'url'} — l'app ouvre `url` en WebView.
    """
    base = _base_url()
    # 1) Créer la transaction
    tx_resp = requests.post(
        f'{base}/v1/transactions',
        headers=_headers(),
        json={
            'description': description,
            'amount': amount,
            'currency': {'iso': currency},
            'callback_url': callback_url,
            'customer': {'email': customer_email} if customer_email else {},
        },
        timeout=20,
    )
    tx_resp.raise_for_status()
    tx = tx_resp.json().get('v1/transaction') or tx_resp.json().get('transaction') or {}
    fedapay_id = str(tx.get('id', ''))

    # 2) Générer le token/URL de paiement
    token_resp = requests.post(
        f'{base}/v1/transactions/{fedapay_id}/token',
        headers=_headers(),
        timeout=20,
    )
    token_resp.raise_for_status()
    data = token_resp.json()
    return {
        'fedapay_id': fedapay_id,
        'token': data.get('token', ''),
        'url': data.get('url', ''),
    }


def get_transaction_status(fedapay_id: str) -> str:
    """Statut réel d'une transaction chez FedaPay (en minuscules).

    Sert de source de vérité quand le webhook n'a pas été reçu (endpoint
    /api/confirm, commande reconcile_fedapay). Retourne '' si introuvable.
    """
    base = _base_url()
    resp = requests.get(
        f'{base}/v1/transactions/{fedapay_id}', headers=_headers(), timeout=20)
    resp.raise_for_status()
    data = resp.json()
    tx = data.get('v1/transaction') or data.get('transaction') or {}
    return (tx.get('status') or '').lower()


def verify_webhook_signature(payload: bytes, signature: str) -> bool:
    """Vérifie la signature HMAC du webhook (header X-FEDAPAY-SIGNATURE)."""
    secret = settings.FEDAPAY_WEBHOOK_SECRET
    if not secret or not signature:
        return False
    computed = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    # FedaPay envoie souvent 't=...,s=...' ; on compare au mieux.
    return hmac.compare_digest(computed, signature) or computed in signature
