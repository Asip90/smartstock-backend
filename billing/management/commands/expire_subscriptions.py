"""Expiration des abonnements + rappels avant échéance (FCM).

Remplace une Cloud Function planifiée (plan Firebase gratuit -> pas de Functions).
À lancer une fois par jour via cron, p. ex. le matin :
    0 9 * * * cd /chemin/backend && .venv/bin/python manage.py expire_subscriptions

Pour chaque doc `subscriptions/{uid}` :
  - calcule le nombre de jours restants avant `currentPeriodEnd` ;
  - envoie UN rappel par palier (3 jours, 1 jour, expiré) — jamais deux fois le
    même palier grâce au champ `expiryReminderStage` ;
  - quand la période est dépassée, bascule `status` -> `expired` (côté serveur ;
    l'app calcule déjà l'accès via `currentPeriodEnd`, mais on garde le statut juste) ;
  - se ré-arme tout seul après un renouvellement (currentPeriodEnd repoussé).

Les rappels d'abonnement sont des messages "transactionnels" : ils ne dépendent
PAS des toggles d'alerte stock/ventes (qui concernent un autre usage).
"""
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from billing import firebase_service as fb

# Paliers de rappel (en jours restants). Ordre décroissant d'urgence.
STAGE_SOON = 'soon'        # <= 3 jours
STAGE_LAST = 'last'        # <= 1 jour
STAGE_EXPIRED = 'expired'  # période dépassée


def _target_stage(days_left: float):
    """Palier visé selon les jours restants, ou None si rien à envoyer."""
    if days_left <= 0:
        return STAGE_EXPIRED
    if days_left <= 1:
        return STAGE_LAST
    if days_left <= 3:
        return STAGE_SOON
    return None


def _message(stage: str, days_left: int):
    if stage == STAGE_EXPIRED:
        return ("Abonnement Pro expiré",
                "Renouvelez pour réactiver les fonctions Pro de Compa.")
    if stage == STAGE_LAST:
        return ("Votre abonnement Pro expire demain",
                "Renouvelez pour ne pas perdre l'accès aux fonctions Pro.")
    return ("Votre abonnement Pro expire bientôt",
            f"Il reste {days_left} jour(s). Renouvelez pour garder l'accès Pro.")


class Command(BaseCommand):
    help = "Expire les abonnements échus et envoie les rappels avant échéance (FCM)."

    def handle(self, *args, **options):
        db = fb.db()
        now = timezone.now()
        sent = 0
        expired = 0

        for doc in db.collection('subscriptions').stream():
            data = doc.to_dict() or {}
            uid = doc.id
            status = (data.get('status') or '').lower()
            period_end = data.get('currentPeriodEnd')

            # Comptes sans échéance (grâce / jamais abonnés) : rien à faire.
            if period_end is None:
                continue
            # Déjà marqué expiré ET rappel "expired" déjà émis : on passe.
            # (on continue quand même à traiter pour le ré-armement post-renouvellement)

            # Propage proUntil aux boutiques possédées (couvre expiration ET
            # ré-armement post-renouvellement), même sans autre mise à jour.
            fb.mirror_pro_to_shops(uid, period_end)

            days_left = (period_end - now).total_seconds() / 86400.0
            current_stage = data.get('expiryReminderStage') or ''
            target = _target_stage(days_left)

            updates = {}

            # Ré-armement : période repoussée au-delà de 3 jours -> on oublie les
            # paliers déjà notifiés pour pouvoir re-notifier au prochain cycle.
            if target is None:
                if current_stage:
                    updates['expiryReminderStage'] = ''
                if updates:
                    db.collection('subscriptions').document(uid).set(updates, merge=True)
                continue

            # Bascule du statut une fois la période dépassée.
            if target == STAGE_EXPIRED and status in ('active', 'trialing'):
                updates['status'] = 'expired'
                expired += 1

            # Nouveau palier -> on notifie une seule fois.
            if target != current_stage:
                title, body = _message(target, max(0, int(days_left)))
                tokens = fb.tokens_for_uid(uid)
                sent += fb.send_push(
                    tokens, title, body,
                    data={'type': 'subscription', 'stage': target},
                )
                updates['expiryReminderStage'] = target

            if updates:
                db.collection('subscriptions').document(uid).set(updates, merge=True)

        self.stdout.write(self.style.SUCCESS(
            f"Abonnements : {expired} expiré(s), {sent} rappel(s) envoyé(s)."))
