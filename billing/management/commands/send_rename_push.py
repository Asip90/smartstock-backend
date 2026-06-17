"""Annonce du changement de nom « SmartStock devient Compa » à TOUS les
utilisateurs (FCM).

Notification d'information simple (pas de mise à jour forcée, pas d'URL : un tap
ouvre juste l'application). Le nom et le logo affichés ont déjà changé côté app
via une mise à jour ; ce push prévient les utilisateurs du nouveau nom.

Action de masse : DRY-RUN par défaut (rien n'est envoyé). Ajouter ``--confirm``
pour réellement envoyer.

    python manage.py send_rename_push            # dry-run
    python manage.py send_rename_push --confirm  # envoi réel
"""
from django.core.management.base import BaseCommand

from billing import firebase_service as fb

DEFAULT_TITLE = "SmartStock devient Compa"
DEFAULT_BODY = (
    "Même application, même équipe, nouveau nom. Merci de votre confiance !")
FCM_MULTICAST_LIMIT = 500


class Command(BaseCommand):
    help = "Annonce le renommage en Compa à tous les utilisateurs (FCM)."

    def add_arguments(self, parser):
        parser.add_argument(
            '--confirm', action='store_true',
            help="Envoie réellement les notifications (sinon dry-run).")
        parser.add_argument('--title', default=DEFAULT_TITLE)
        parser.add_argument('--body', default=DEFAULT_BODY)

    def handle(self, *args, **options):
        db = fb.db()
        title = options['title']
        body = options['body']

        tokens = [d.id for d in db.collection('fcm_tokens').stream()]
        self.stdout.write(f"Jetons FCM trouvés : {len(tokens)}")
        self.stdout.write(f"Titre : {title}")
        self.stdout.write(f"Corps : {body}")

        if not options['confirm']:
            self.stdout.write(self.style.WARNING(
                "DRY-RUN : aucune notification envoyée. "
                "Relancer avec --confirm pour envoyer."))
            return

        sent = 0
        for i in range(0, len(tokens), FCM_MULTICAST_LIMIT):
            batch = tokens[i:i + FCM_MULTICAST_LIMIT]
            sent += fb.send_push(batch, title, body, data={'type': 'rename'})

        self.stdout.write(self.style.SUCCESS(
            f"Annonces de renommage envoyées : {sent}"))
