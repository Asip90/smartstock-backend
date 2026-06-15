"""Briefing du matin par notification push (FCM).

Notifie le propriétaire et les membres ayant activé « briefing du matin »
(users/{uid}/settings/notifications.notif_morning_briefing), avec un résumé
des ventes d'hier, des ruptures de stock actuelles et des dettes clients.

À planifier le matin via cron, p. ex. :
    0 7 * * * cd /chemin/backend && python manage.py send_morning_briefing
"""
from django.core.management.base import BaseCommand

from billing import firebase_service as fb
from billing import notif_engine
from billing import notif_facts


class Command(BaseCommand):
    help = "Envoie le briefing du matin aux commerçants (FCM)."

    def handle(self, *args, **options):
        db = fb.db()
        total_sent = 0

        for shop in db.collection('shops').stream():
            shop_id = shop.id
            shop_data = shop.to_dict() or {}
            owner_id = shop_data.get('ownerId')

            facts = notif_facts.morning_facts(db, shop_id, shop_data)

            if (facts['yesterday_count'] == 0
                    and facts['ruptures_count'] == 0
                    and not facts.get('debts_total')):
                continue

            fallback_title = f"Bonjour — {facts['shop_name']}"

            parts = []
            if facts['yesterday_count'] > 0:
                parts.append(
                    f"hier : {facts['yesterday_count']} vente(s) · "
                    f"CA {facts['yesterday_revenue']:,.0f} FCFA"
                )
            if facts['ruptures_count'] > 0:
                sample = ', '.join(facts['ruptures_samples'])
                parts.append(
                    f"{facts['ruptures_count']} produit(s) en rupture : {sample}"
                    + ('…' if facts['ruptures_count'] > 3 else '')
                )
            if facts.get('debts_total'):
                parts.append(
                    f"{facts.get('debts_count', 0)} client(s) à relancer · "
                    f"{facts['debts_total']:,.0f} FCFA à recouvrer"
                )

            fallback_body = ' · '.join(parts)
            fallback_body = fallback_body.replace(',', ' ')  # séparateur de milliers en espace

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
                if not fb.notif_settings(uid).get('notif_morning_briefing', True):
                    continue
                recipient_facts = {**facts, 'first_name': notif_facts.first_name(db, uid)}
                total_sent += notif_engine.compose_and_send(
                    uid=uid, kind='morning', facts=recipient_facts,
                    fallback_title=fallback_title, fallback_body=fallback_body,
                    push_data={'type': 'morning_briefing', 'shopId': shop_id},
                )

        self.stdout.write(self.style.SUCCESS(
            f"Briefings du matin envoyés : {total_sent}"))
