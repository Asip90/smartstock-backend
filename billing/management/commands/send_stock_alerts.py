"""Alerte de stock critique par notification push (FCM).

Parcourt les boutiques, repère les produits sous le seuil critique et notifie
le propriétaire et les membres qui ont gardé l'alerte « stock critique » active
(users/{uid}/settings/notifications.notif_critical_stock).

À planifier via cron, p. ex. une fois par jour :
    0 8 * * * cd /chemin/backend && python manage.py send_stock_alerts
"""
from django.core.management.base import BaseCommand

from billing import firebase_service as fb
from billing import notif_engine
from billing import notif_facts


class Command(BaseCommand):
    help = "Envoie les alertes de stock critique aux commerçants (FCM)."

    def handle(self, *args, **options):
        db = fb.db()
        shops = list(db.collection('shops').stream())
        total_sent = 0

        for shop in shops:
            shop_id = shop.id
            shop_data = shop.to_dict() or {}
            owner_id = shop_data.get('ownerId')

            facts = notif_facts.stock_facts(db, shop_id, shop_data)

            if facts['count'] == 0:
                continue

            # Destinataires : propriétaire + membres actifs.
            recipients = set()
            if owner_id:
                recipients.add(owner_id)
            for m in db.collection('shops').document(shop_id).collection('members').stream():
                md = m.to_dict() or {}
                uid = md.get('userId') or m.id
                if uid:
                    recipients.add(uid)

            title = f"Stock critique — {shop_data.get('name', 'votre boutique')}"
            count = facts['count']
            sample = ', '.join(facts['samples'])
            body = (f"{count} produit(s) en stock faible : {sample}"
                    + ('…' if count > 3 else ''))

            for uid in recipients:
                if not fb.notif_settings(uid).get('notif_critical_stock', True):
                    continue
                recipient_facts = {**facts, 'first_name': notif_facts.first_name(db, uid)}
                total_sent += notif_engine.compose_and_send(
                    uid=uid, kind='stock', facts=recipient_facts,
                    fallback_title=title, fallback_body=body,
                    push_data={'type': 'critical_stock', 'shopId': shop_id},
                )

        self.stdout.write(self.style.SUCCESS(
            f"Alertes stock critique envoyées : {total_sent}"))
