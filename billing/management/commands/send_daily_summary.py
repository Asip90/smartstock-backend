"""Résumé quotidien des ventes par notification push (FCM).

Notifie le propriétaire et les membres ayant activé « résumé quotidien »
(users/{uid}/settings/notifications.notif_daily_summary).

À planifier le soir via cron, p. ex. :
    0 20 * * * cd /chemin/backend && python manage.py send_daily_summary
"""
from datetime import datetime, time

from django.core.management.base import BaseCommand
from django.utils import timezone

from billing import firebase_service as fb


class Command(BaseCommand):
    help = "Envoie le résumé quotidien des ventes aux commerçants (FCM)."

    def handle(self, *args, **options):
        db = fb.db()
        now = timezone.localtime()
        start = timezone.make_aware(datetime.combine(now.date(), time.min))
        total_sent = 0

        for shop in db.collection('shops').stream():
            shop_id = shop.id
            data = shop.to_dict() or {}
            owner_id = data.get('ownerId')

            revenue = 0.0
            cash = 0.0
            count = 0
            sales = (db.collection('sales')
                     .where('shopId', '==', shop_id)
                     .where('saleDate', '>=', start)
                     .stream())
            for s in sales:
                sd = s.to_dict() or {}
                total = float(sd.get('totalAmount', 0) or 0)
                paid = sd.get('amountPaid')
                paid = float(paid) if paid is not None else total
                revenue += total
                cash += paid
                count += 1

            if count == 0:
                continue

            credit = revenue - cash
            title = f"Bilan du jour — {data.get('name', 'votre boutique')}"
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
                tokens = fb.tokens_for_uid(uid)
                total_sent += fb.send_push(
                    tokens, title, body,
                    data={'type': 'daily_summary', 'shopId': shop_id},
                )

        self.stdout.write(self.style.SUCCESS(
            f"Résumés quotidiens envoyés : {total_sent}"))
