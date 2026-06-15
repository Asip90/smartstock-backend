"""Résumé quotidien des ventes par notification push (FCM).

Notifie le propriétaire et les membres ayant activé « résumé quotidien »
(users/{uid}/settings/notifications.notif_daily_summary).

À planifier le soir via cron, p. ex. :
    0 20 * * * cd /chemin/backend && python manage.py send_daily_summary
"""
from django.core.management.base import BaseCommand

from billing import firebase_service as fb
from billing import notif_engine
from billing import notif_facts


class Command(BaseCommand):
    help = "Envoie le résumé quotidien des ventes aux commerçants (FCM)."

    def handle(self, *args, **options):
        db = fb.db()
        total_sent = 0

        for shop in db.collection('shops').stream():
            shop_id = shop.id
            shop_data = shop.to_dict() or {}
            owner_id = shop_data.get('ownerId')

            facts = notif_facts.evening_facts(db, shop_id, shop_data)

            if facts['count'] == 0:
                continue

            count = facts['count']
            revenue = facts['revenue']
            cash = facts['cash']
            credit = facts['credit']

            title = f"Bilan du jour — {shop_data.get('name', 'votre boutique')}"
            body = (f"{count} vente(s) · CA {revenue:,.0f} FCFA · "
                    f"encaissé {cash:,.0f}"
                    + (f" · à crédit {credit:,.0f}" if credit > 0 else ""))
            body = body.replace(',', ' ')  # séparateur de milliers en espace

            recipients = set()
            if owner_id:
                recipients.add(owner_id)
            for m in (db.collection('shops').document(shop_id)
                      .collection('members').stream()):
                md = m.to_dict() or {}
                recipients.add(md.get('userId') or m.id)

            for uid in recipients:
                if not uid:
                    continue
                if not fb.notif_settings(uid).get('notif_daily_summary', False):
                    continue
                recipient_facts = {**facts, 'first_name': notif_facts.first_name(db, uid)}
                total_sent += notif_engine.compose_and_send(
                    uid=uid, kind='evening', facts=recipient_facts,
                    fallback_title=title, fallback_body=body,
                    push_data={'type': 'daily_summary', 'shopId': shop_id},
                )

        self.stdout.write(self.style.SUCCESS(
            f"Résumés quotidiens envoyés : {total_sent}"))
