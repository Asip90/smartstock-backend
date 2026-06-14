"""Initialisation Firebase Admin + vérification de token + écriture de l'entitlement.

L'app Flutter envoie son Firebase ID token ; on le vérifie ici pour obtenir l'uid.
L'entitlement d'abonnement est écrit dans Firestore `subscriptions/{uid}` (écriture
serveur uniquement — les règles interdisent l'écriture client).
"""
import json

import firebase_admin
from firebase_admin import auth as fb_auth
from firebase_admin import credentials, firestore, messaging
from django.conf import settings

_app = None
_db = None


def _ensure_init():
    global _app, _db
    if _app is not None:
        return
    raw = settings.FIREBASE_SERVICE_ACCOUNT_JSON
    if not raw:
        raise RuntimeError('FIREBASE_SERVICE_ACCOUNT_JSON manquant')
    # Accepte un JSON inline ou un chemin de fichier.
    if raw.strip().startswith('{'):
        cred = credentials.Certificate(json.loads(raw))
    else:
        cred = credentials.Certificate(raw)
    _app = firebase_admin.initialize_app(cred)
    _db = firestore.client()


def verify_token(id_token: str):
    """Retourne (uid, email) ou lève une exception si le token est invalide."""
    _ensure_init()
    decoded = fb_auth.verify_id_token(id_token)
    return decoded['uid'], decoded.get('email', '')


def set_entitlement(uid: str, *, plan: str, status: str,
                    trial_end=None, current_period_end=None):
    """Écrit/merge l'entitlement dans Firestore subscriptions/{uid}."""
    _ensure_init()
    data = {'plan': plan, 'status': status, 'updatedAt': firestore.SERVER_TIMESTAMP}
    if trial_end is not None:
        data['trialEnd'] = trial_end
    if current_period_end is not None:
        data['currentPeriodEnd'] = current_period_end
    _db.collection('subscriptions').document(uid).set(data, merge=True)


def get_entitlement(uid: str):
    _ensure_init()
    doc = _db.collection('subscriptions').document(uid).get()
    return doc.to_dict() if doc.exists else None


def db():
    """Client Firestore initialisé (pour les tâches d'envoi de notifications)."""
    _ensure_init()
    return _db


def tokens_for_uid(uid: str):
    """Jetons FCM enregistrés pour un utilisateur (collection fcm_tokens)."""
    _ensure_init()
    docs = _db.collection('fcm_tokens').where('userId', '==', uid).stream()
    return [d.id for d in docs]


def notif_settings(uid: str):
    """Réglages de notifications de l'utilisateur (users/{uid}/settings/notifications).
    Renvoie un dict ; par défaut les alertes critiques sont actives."""
    _ensure_init()
    doc = (_db.collection('users').document(uid)
           .collection('settings').document('notifications').get())
    data = doc.to_dict() if doc.exists else {}
    return {
        'notif_critical_stock': data.get('notif_critical_stock', True),
        'notif_new_sale': data.get('notif_new_sale', True),
        'notif_daily_summary': data.get('notif_daily_summary', False),
    }


def send_push(tokens, title: str, body: str, data: dict | None = None):
    """Envoie une notification à une liste de jetons (multicast). Retourne le
    nombre d'envois réussis. Nettoie les jetons devenus invalides."""
    _ensure_init()
    tokens = [t for t in tokens if t]
    if not tokens:
        return 0
    message = messaging.MulticastMessage(
        tokens=tokens,
        notification=messaging.Notification(title=title, body=body),
        data={k: str(v) for k, v in (data or {}).items()},
    )
    resp = messaging.send_each_for_multicast(message)
    # Supprime les jetons rejetés (désinstallation, expiration).
    for tok, r in zip(tokens, resp.responses):
        if not r.success:
            try:
                _db.collection('fcm_tokens').document(tok).delete()
            except Exception:
                pass
    return resp.success_count


def set_app_config(*, latest_build: int, min_build: int, message: str, store_url: str):
    """Écrit la config de mise à jour de l'app mobile dans Firestore `config/app`.
    L'app lit ce doc au démarrage : `latest_build` > build courant -> MAJ proposée ;
    build courant < `min_build` -> MAJ OBLIGATOIRE (dialogue bloquant)."""
    _ensure_init()
    _db.collection('config').document('app').set({
        'latest_build': int(latest_build),
        'min_build': int(min_build),
        'message': message or '',
        'store_url': store_url or '',
    }, merge=True)
