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


def create_payout(*, amount: int, firstname: str, lastname: str,
                   phone_number: str, phone_country: str, currency: str = 'XOF'):
    """Crée un payout (transfert du solde marchand FedaPay vers un numéro
    Mobile Money) — utilisé pour reverser aux propriétaires de boutique
    (cf. design solde & retraits). Jamais appelé automatiquement : toujours
    déclenché par une validation humaine (page admin dédiée).

    Retourne {'fedapay_id', 'status', 'fees', 'amount_debited',
    'amount_transferred'}. `amount_debited`/`fees` reflètent le coût réel
    facturé par FedaPay — jamais devinés côté app, toujours lus depuis la
    réponse (repli sûr sur `amount` si l'API ne les renvoie pas)."""
    base = _base_url()
    resp = requests.post(
        f'{base}/v1/payouts',
        headers=_headers(),
        json={
            'amount': amount,
            'currency': {'iso': currency},
            'mode': 'mobile_money',
            'customer': {
                'firstname': firstname,
                'lastname': lastname,
                'phone_number': {'number': phone_number, 'country': phone_country},
            },
        },
        timeout=20,
    )
    resp.raise_for_status()
    data = resp.json()
    payout = data.get('v1/payout') or data.get('payout') or {}
    amount_transferred = payout.get('amount_transferred', amount)
    return {
        'fedapay_id': str(payout.get('id', '')),
        'status': (payout.get('status') or '').lower(),
        'fees': payout.get('fees', 0),
        'amount_debited': payout.get('amount_debited', amount_transferred),
        'amount_transferred': amount_transferred,
    }


def verify_webhook_signature(payload: bytes, signature: str, *, secret: str | None = None) -> bool:
    """Vérifie la signature HMAC du webhook (header X-FEDAPAY-SIGNATURE).

    Chaque endpoint webhook FedaPay a SON PROPRE secret (généré séparément
    à la création de chaque webhook dans le dashboard) — jamais le même
    entre l'abonnement Pro et la boutique en ligne. Repli sur
    `FEDAPAY_WEBHOOK_SECRET` (abonnement) si `secret` n'est pas fourni,
    pour ne pas casser l'appelant existant `billing/views.py::webhook`."""
    secret = secret if secret is not None else settings.FEDAPAY_WEBHOOK_SECRET
    if not secret or not signature:
        return False
    computed = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    # FedaPay envoie souvent 't=...,s=...' ; on compare au mieux.
    return hmac.compare_digest(computed, signature) or computed in signature
