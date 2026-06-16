"""Bilan hebdomadaire par notification push (FCM).

Notifie le propriétaire et les membres ayant activé « bilan hebdomadaire »
(users/{uid}/settings/notifications.notif_weekly_recap), avec une comparaison
du CA de la semaine en cours vs la précédente, le nombre de ventes et le
meilleur jour de la semaine.

Par défaut la commande tourne à blanc (dry-run) : elle calcule et affiche les
bilans SANS rien envoyer. Passer ``--commit`` pour réellement envoyer.

À planifier le dimanche soir via cron, p. ex. :
    0 20 * * 0 cd /chemin/backend && python manage.py send_weekly_recap --commit
"""
from django.core.management.base import BaseCommand

from billing import firebase_service as fb
from billing import notif_engine
from billing import notif_facts


def _fmt(value) -> str:
    """Formate un montant FCFA avec un espace comme séparateur de milliers."""
    return f"{value:,.0f}".replace(',', ' ')


class Command(BaseCommand):
    help = ("Envoie le bilan hebdomadaire aux commerçants (FCM). "
            "Tourne à blanc par défaut ; utiliser --commit pour envoyer.")

    def add_arguments(self, parser):
        parser.add_argument(
            '--commit', action='store_true', default=False,
            help="Envoie réellement les notifications (sinon dry-run).",
        )

    def handle(self, *args, **options):
        commit = options['commit']
        db = fb.db()
        total_sent = 0
        shops_with_sales = 0

        for shop in db.collection('shops').stream():
            shop_id = shop.id
            shop_data = shop.to_dict() or {}
            owner_id = shop_data.get('ownerId')

            facts = notif_facts.weekly_facts(db, shop_id, shop_data)

            if facts['count'] == 0:
                continue
            shops_with_sales += 1

            fallback_title = "Ton bilan de la semaine"

            parts = [
                f"{facts['count']} vente(s) · CA {_fmt(facts['revenue'])} FCFA"
            ]
            growth = facts.get('growth')
            if growth is not None:
                sign = '+' if growth >= 0 else ''
                parts.append(
                    f"{sign}{growth:.0f}% vs semaine dernière "
                    f"({_fmt(facts['prev_revenue'])} FCFA)"
                )
            elif facts.get('prev_revenue', 0) == 0:
                parts.append("première semaine de ventes")
            if facts.get('best_day'):
                parts.append(
                    f"meilleur jour : {facts['best_day']} "
                    f"({_fmt(facts['best_day_revenue'])} FCFA)"
                )

            fallback_body = ' · '.join(parts)

            # Destinataires : propriétaire + membres actifs.
            recipients = set()
            if owner_id:
                recipients.add(owner_id)
            for m in (db.collection('shops').document(shop_id)
                      .collection('members').stream()):
                md = m.to_dict() or {}
                uid = md.get('userId') or m.id
                if uid:
                    recipients.add(uid)

            for uid in recipients:
                if not fb.notif_settings(uid).get('notif_weekly_recap', True):
                    continue

                if not commit:
                    self.stdout.write(
                        f"[dry-run] {shop_data.get('name', shop_id)} → {uid} : "
                        f"{fallback_body}"
                    )
                    continue

                recipient_facts = {
                    **facts, 'first_name': notif_facts.first_name(db, uid)}
                total_sent += notif_engine.compose_and_send(
                    uid=uid, kind='weekly', facts=recipient_facts,
                    fallback_title=fallback_title, fallback_body=fallback_body,
                    push_data={'type': 'weekly_recap', 'shopId': shop_id},
                )

        if commit:
            self.stdout.write(self.style.SUCCESS(
                f"Bilans hebdomadaires envoyés : {total_sent} "
                f"({shops_with_sales} boutique(s) avec ventes)"))
        else:
            self.stdout.write(self.style.WARNING(
                f"[dry-run] {shops_with_sales} boutique(s) avec ventes. "
                f"Aucune notification envoyée (passer --commit pour envoyer)."))
