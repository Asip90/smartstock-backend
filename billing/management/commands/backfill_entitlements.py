"""Grand-fathering : garantit un entitlement d'abonnement pour tout compte existant.

Contexte : l'app considérait historiquement « pas de doc subscriptions/{uid} » comme
« Pro gratuit ». On veut fermer cette faille sans verrouiller les utilisateurs déjà
présents. Cette commande crée un doc d'entitlement Pro (durée de grâce) pour chaque
UID connu qui n'en possède pas encore.

À lancer une seule fois (idéalement en dry-run d'abord) :
    .venv/bin/python manage.py backfill_entitlements            # dry-run (n'écrit rien)
    .venv/bin/python manage.py backfill_entitlements --commit   # applique les écritures
    .venv/bin/python manage.py backfill_entitlements --commit --days 30

Les UID sont collectés depuis Firebase Auth (tous les comptes, via `list_all_uids`)
ET la base (transactions + parrainages). Si Firebase Auth est injoignable, repli
automatique sur les seuls UID présents en base (avec un avertissement).
"""
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from billing import firebase_service as fb
from billing.models import Referral, Transaction


def _known_uids(stdout=None):
    """Ensemble dédupliqué des UID à couvrir.

    Source principale : tous les comptes Firebase Auth (`list_all_uids`), qui inclut
    les utilisateurs jamais vus en base. En complément (et en repli si Firebase Auth
    est injoignable), l'union des UID présents en base (transactions + parrainages).
    """
    uids = set(Transaction.objects.values_list('uid', flat=True))
    uids |= set(Referral.objects.values_list('referred_uid', flat=True))
    try:
        uids |= set(fb.list_all_uids())
    except Exception as e:  # pragma: no cover - dépend de l'environnement Firebase
        if stdout is not None:
            stdout.write(
                f"[avertissement] Firebase Auth injoignable ({e}); "
                "repli sur les UID présents en base uniquement.")
    # On retire les valeurs vides / None.
    return {u for u in uids if u}


class Command(BaseCommand):
    help = ("Crée un entitlement Pro (durée de grâce) pour chaque UID connu qui n'en "
            "possède pas encore. Dry-run par défaut ; --commit pour écrire.")

    def add_arguments(self, parser):
        parser.add_argument(
            '--days', type=int, default=30,
            help="Durée de grâce en jours pour currentPeriodEnd (défaut : 30).")
        parser.add_argument(
            '--commit', action='store_true', default=False,
            help="Applique réellement les écritures (sinon dry-run, n'écrit rien).")

    def handle(self, *args, **options):
        days = options['days']
        commit = options['commit']

        uids = _known_uids(self.stdout)
        period_end = timezone.now() + timedelta(days=days)

        total = len(uids)
        already = 0
        backfilled = 0

        for uid in sorted(uids):
            if fb.get_entitlement(uid):
                already += 1
                continue
            backfilled += 1
            if commit:
                fb.set_entitlement(
                    uid,
                    plan='pro',
                    status='active',
                    current_period_end=period_end,
                )
                fb.mirror_pro_to_shops(uid, period_end)
                self.stdout.write(f"Backfill : {uid}")
            else:
                self.stdout.write(f"[dry-run] Backfill prévu : {uid}")

        mode = "écrits" if commit else "à écrire (dry-run)"
        self.stdout.write(self.style.SUCCESS(
            f"UID connus : {total} | déjà un doc : {already} | "
            f"{backfilled} entitlement(s) {mode}."))
