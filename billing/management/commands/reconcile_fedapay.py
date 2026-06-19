"""Réconcilie les transactions FedaPay restées `pending` en local mais réellement
approuvées chez FedaPay.

Contexte : la confirmation de paiement (entitlement + commission) dépendait du seul
webhook FedaPay. Si le webhook n'est pas reçu (non configuré côté dashboard, panne,
retard), des paiements encaissés restent `pending` et aucune commission n'est créée.
Cette commande interroge FedaPay pour chaque transaction `pending` et confirme
celles qui sont approuvées, via la même logique que le webhook
(`_apply_paid_transaction`, idempotente).

À lancer ponctuellement (rattrapage) ou en cron (filet de sécurité) :
    venv/bin/python manage.py reconcile_fedapay            # dry-run (n'écrit rien)
    venv/bin/python manage.py reconcile_fedapay --commit   # confirme réellement
"""
from django.core.management.base import BaseCommand

from billing import fedapay
from billing.models import Transaction
from billing.views import FEDAPAY_PAID_STATUSES, _apply_paid_transaction


class Command(BaseCommand):
    help = ("Confirme les transactions `pending` réellement approuvées chez FedaPay. "
            "Dry-run par défaut ; --commit pour appliquer.")

    def add_arguments(self, parser):
        parser.add_argument(
            '--commit', action='store_true', default=False,
            help="Applique réellement les confirmations (sinon dry-run).")

    def handle(self, *args, **options):
        commit = options['commit']
        pending = Transaction.objects.filter(status='pending').exclude(fedapay_id='')

        checked = confirmed = errors = 0
        for tx in pending.order_by('created_at'):
            checked += 1
            try:
                status = fedapay.get_transaction_status(tx.fedapay_id)
            except Exception as e:  # réseau / API FedaPay
                errors += 1
                self.stdout.write(self.style.WARNING(
                    f"tx {tx.id} ({tx.fedapay_id}) : erreur FedaPay : {e}"))
                continue

            if status not in FEDAPAY_PAID_STATUSES:
                continue

            confirmed += 1
            if commit:
                _apply_paid_transaction(tx)
                self.stdout.write(
                    f"Confirmée : tx {tx.id} {tx.email} {tx.plan} {tx.amount} F")
            else:
                self.stdout.write(
                    f"[dry-run] À confirmer : tx {tx.id} {tx.email} "
                    f"{tx.plan} {tx.amount} F (FedaPay={status})")

        mode = "confirmée(s)" if commit else "à confirmer (dry-run)"
        self.stdout.write(self.style.SUCCESS(
            f"Transactions pending vérifiées : {checked} | "
            f"{confirmed} {mode} | erreurs : {errors}."))
