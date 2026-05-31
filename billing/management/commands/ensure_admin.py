import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    """Crée (ou met à jour) un super-utilisateur à partir des variables
    d'environnement, sans avoir besoin d'un Shell.

    Variables lues :
      DJANGO_SUPERUSER_USERNAME (defaut: admin)
      DJANGO_SUPERUSER_PASSWORD (obligatoire pour creer le compte)
      DJANGO_SUPERUSER_EMAIL    (optionnel)

    Idempotent : si le compte existe deja, le mot de passe est resynchronise.
    """

    help = "Cree un superuser depuis les variables d'environnement (sans shell)."

    def handle(self, *args, **options):
        User = get_user_model()
        username = os.environ.get('DJANGO_SUPERUSER_USERNAME', 'admin').strip()
        password = os.environ.get('DJANGO_SUPERUSER_PASSWORD', '').strip()
        email = os.environ.get('DJANGO_SUPERUSER_EMAIL', '').strip()

        if not password:
            self.stdout.write(self.style.WARNING(
                "DJANGO_SUPERUSER_PASSWORD non defini : aucun admin cree."))
            return

        user, created = User.objects.get_or_create(username=username)
        user.email = email or user.email
        user.is_staff = True
        user.is_superuser = True
        user.set_password(password)
        user.save()

        if created:
            self.stdout.write(self.style.SUCCESS(f"Superuser '{username}' cree."))
        else:
            self.stdout.write(self.style.SUCCESS(
                f"Superuser '{username}' deja present : mot de passe resynchronise."))
