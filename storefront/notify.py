"""Notifie le propriétaire d'une boutique à la création d'une commande en
ligne — réutilise l'infrastructure push déjà en production
(`billing/firebase_service.py`), même pattern que `billing/notifications.py`."""
from billing import firebase_service as fb_service

from . import firebase_read as fb_read


def notify_new_order(shop_id: str, shop_name: str, order_id: str,
                      total_amount: float) -> None:
    """Push + historique au propriétaire de `shop_id`. Ne fait rien
    (silencieusement) si le propriétaire ne peut pas être résolu — une
    commande déjà écrite dans Firestore ne doit jamais être perdue/annulée
    à cause d'un échec de notification, seulement le push est manqué."""
    owner_uid = fb_read.get_shop_owner_uid(shop_id)
    if owner_uid is None:
        return
    tokens = fb_service.tokens_for_uid(owner_uid)
    title = f'{shop_name} : nouvelle commande'
    body = f'Nouvelle commande en ligne de {total_amount:.0f}'
    data = {'type': 'new_online_order', 'orderId': order_id, 'shopId': shop_id}
    fb_service.send_push(tokens, title, body, data)
    fb_service.record_notification(
        owner_uid, title=title, body=body, data=data, ntype='new_online_order')
