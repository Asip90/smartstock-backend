"""Envoi ciblé d'une notification push à un utilisateur précis (page admin).

Résout un destinataire (uid ou email) en uid Firebase, envoie le push à tous
ses jetons, puis écrit l'historique Firestore (users/{uid}/notifications)."""
from firebase_admin import auth as fb_auth

from . import firebase_service


def send_targeted_notification(recipient: str, title: str,
                               body: str) -> tuple[int, str]:
    """Envoie une notif à `recipient` (uid OU email). Retourne
    (nombre d'envois réussis, uid résolu)."""
    firebase_service._ensure_init()
    recipient = recipient.strip()
    if '@' in recipient:
        uid = fb_auth.get_user_by_email(recipient).uid
    else:
        uid = recipient
    tokens = firebase_service.tokens_for_uid(uid)
    count = firebase_service.send_push(tokens, title, body, {'type': 'admin'})
    firebase_service.record_notification(
        uid, title=title, body=body, data={'type': 'admin'}, ntype='admin')
    return count, uid
