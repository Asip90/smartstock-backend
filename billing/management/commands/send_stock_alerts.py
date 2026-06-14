"""Alerte de stock critique par notification push (FCM).

Parcourt les boutiques, repère les produits sous le seuil critique et notifie
le propriétaire et les membres qui ont gardé l'alerte « stock critique » active
(users/{uid}/settings/notifications.notif_critical_stock).

À planifier via cron, p. ex. une fois par jour :
    0 8 * * * cd /chemin/backend && python manage.py send_stock_alerts
"""
from django.core.management.base import BaseCommand

from billing import firebase_service as fb

DEFAULT_THRESHOLD = 5  # repli si nbreCritique non défini (aligné sur l'app)


class Command(BaseCommand):
    help = "Envoie les alertes de stock critique aux commerçants (FCM)."

    def handle(self, *args, **options):
        db = fb.db()
        shops = list(db.collection('shops').stream())
        total_sent = 0

        for shop in shops:
            shop_id = shop.id
            data = shop.to_dict() or {}
            owner_id = data.get('ownerId')

            # Produits sous le seuil critique (comparaison à deux champs -> en Python).
            low = []
            for p in db.collection('produits').where('shopId', '==', shop_id).stream():
                pd = p.to_dict() or {}
                qty = pd.get('quantity', 0) or 0
                threshold = pd.get('nbreCritique') or DEFAULT_THRESHOLD
                if qty <= threshold:
                    low.append((pd.get('name', 'Produit'), qty))

            if not low:
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

            title = f"Stock critique — {data.get('name', 'votre boutique')}"
            count = len(low)
            sample = ', '.join(n for n, _ in low[:3])
            body = (f"{count} produit(s) en stock faible : {sample}"
                    + ('…' if count > 3 else ''))

            for uid in recipients:
                if not fb.notif_settings(uid).get('notif_critical_stock', True):
                    continue
                tokens = fb.tokens_for_uid(uid)
                sent = fb.send_push(
                    tokens, title, body,
                    data={'type': 'critical_stock', 'shopId': shop_id},
                )
                total_sent += sent

        self.stdout.write(self.style.SUCCESS(
            f"Alertes stock critique envoyées : {total_sent}"))
