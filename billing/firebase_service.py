"""Initialisation Firebase Admin + vérification de token + écriture de l'entitlement.

L'app Flutter envoie son Firebase ID token ; on le vérifie ici pour obtenir l'uid.
L'entitlement d'abonnement est écrit dans Firestore `subscriptions/{uid}` (écriture
serveur uniquement — les règles interdisent l'écriture client).
"""
import json

import firebase_admin
from firebase_admin import auth as fb_auth
from firebase_admin import credentials, firestore
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
