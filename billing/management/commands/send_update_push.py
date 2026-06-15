"""Notification push de mise à jour à TOUS les utilisateurs (FCM).

Envoie à tous les jetons enregistrés une notification invitant à mettre à jour
l'application. Au tap, l'app ouvre l'URL de téléchargement (data `url`, issue de
``AppConfig.store_url``). Pour les utilisateurs encore sur une ancienne version,
la mise à jour obligatoire (modale bloquante pilotée par ``AppConfig`` →
Firestore ``config/app``) prend le relais à l'ouverture de l'app.

Action de masse : DRY-RUN par défaut (rien n'est envoyé). Ajouter ``--confirm``
pour réellement envoyer.

    python manage.py send_update_push --confirm
"""
from django.core.management.base import BaseCommand

from billing import firebase_service as fb
from billing.models import AppConfig

DEFAULT_URL = 'https://smartstock.nouyon.site/telecharger'
FCM_MULTICAST_LIMIT = 500


class Command(BaseCommand):
    help = "Envoie une notification de mise à jour à tous les utilisateurs (FCM)."

    def add_arguments(self, parser):
        parser.add_argument(
            '--confirm', action='store_true',
            help="Envoie réellement les notifications (sinon dry-run).")
        parser.add_argument('--title', default="Mise à jour SmartStock")
        parser.add_argument('--body', default=None)

    def handle(self, *args, **options):
        db = fb.db()
        cfg = AppConfig.objects.first()
        store_url = (getattr(cfg, 'store_url', '') or DEFAULT_URL)
        message = (getattr(cfg, 'message', '')
                   or "Une nouvelle version de SmartStock est disponible.")
        title = options['title']
        body = options['body'] or message

        tokens = [d.id for d in db.collection('fcm_tokens').stream()]
        self.stdout.write(f"Jetons FCM trouvés : {len(tokens)}")
        self.stdout.write(f"URL de téléchargement : {store_url}")

        if not options['confirm']:
            self.stdout.write(self.style.WARNING(
                "DRY-RUN : aucune notification envoyée. "
                "Relancer avec --confirm pour envoyer."))
            return

        sent = 0
        for i in range(0, len(tokens), FCM_MULTICAST_LIMIT):
            batch = tokens[i:i + FCM_MULTICAST_LIMIT]
            sent += fb.send_push(
                batch, title, body,
                data={'type': 'app_update', 'url': store_url},
            )

        self.stdout.write(self.style.SUCCESS(
            f"Notifications de mise à jour envoyées : {sent}"))
