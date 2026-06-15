"""Orchestrateur du moteur de notifications IA.

Étant donné des faits déjà calculés (par ``notif_facts``), choisit un angle
non répété, demande au service IA un message court (``ai_service``), retombe
sur un message templaté si l'IA ne répond pas, envoie le push (via
``firebase_service``) et journalise l'envoi (``NotificationLog``).

UNE notification est TOUJOURS envoyée (IA ou repli).
"""
import random

from . import ai_service
from . import firebase_service
from .models import NotificationLog

# Angles possibles par type de notification, utilisés pour varier le ton des
# messages générés par l'IA et éviter la répétition.
ANGLES: dict[str, list[str]] = {
    'morning': ['motivant', 'factuel', 'conseil', 'encouragement'],
    'evening': ['factuel', 'félicitation', 'bilan', 'encouragement'],
    'stock': ['alerte', 'factuel', 'conseil'],
}

# Angles de repli pour un type de notification inconnu.
DEFAULT_ANGLES: list[str] = ['factuel', 'conseil', 'encouragement']


def pick_angle(kind: str, last_angle: str | None) -> str:
    """Choisit un angle aléatoire pour ``kind``, différent de ``last_angle``
    si possible (évite de répéter deux fois de suite le même ton)."""
    angles = ANGLES.get(kind, DEFAULT_ANGLES)
    choices = [a for a in angles if a != last_angle]
    if not choices:
        choices = angles
    return random.choice(choices)


def compose_and_send(*, uid: str, kind: str, facts: dict, fallback_title: str,
                      fallback_body: str, push_data: dict | None = None) -> int:
    """Compose et envoie UNE notification push pour ``uid``.

    Choisit un angle non répété, tente une génération IA du corps du message
    (le titre reste toujours celui fourni en repli), retombe sur
    ``fallback_body`` si l'IA ne répond pas, envoie le push et journalise le
    résultat. Renvoie le nombre d'envois réussis (0 si aucun jeton)."""
    recent, last_angle = NotificationLog.recent_for(uid, kind)
    angle = pick_angle(kind, last_angle)

    generated = ai_service.generate_message(
        kind=kind, facts=facts, recent=recent, angle=angle)

    body = generated or fallback_body
    ai_used = generated is not None

    tokens = firebase_service.tokens_for_uid(uid)
    sent = firebase_service.send_push(
        tokens, fallback_title, body, push_data or {'type': kind})

    NotificationLog.objects.create(
        uid=uid, kind=kind, title=fallback_title, body=body,
        angle=angle, ai_used=ai_used)

    return sent
