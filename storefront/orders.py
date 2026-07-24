"""Construction des lignes de commande (avec re-vérification du stock RÉEL,
jamais une confiance aveugle au panier envoyé par le navigateur) et écriture
de la commande dans Firestore `storeOrders` — écrite par Django, lue et
confirmée par l'app Flutter (cf. spec, section « Confirmation de commande →
vente réelle »)."""
from billing import firebase_service as fb

from . import firebase_read as fb_read


class CartLineError(Exception):
    """Une ligne du panier n'est plus valide au moment du checkout."""

    def __init__(self, product_id: str, product_name: str, reason: str,
                 available: int | None = None):
        self.product_id = product_id
        self.product_name = product_name
        self.reason = reason  # 'unavailable' | 'insufficient_stock'
        self.available = available
        super().__init__(f'{product_id}: {reason}')


def build_order_lines(shop_id: str, cart: dict[str, int]) -> list[dict]:
    """Relit chaque produit du panier depuis Firestore et construit les
    lignes de commande avec le PRIX RÉEL actuel. Lève `CartLineError` sur la
    première ligne invalide (produit supprimé/retiré du public, ou stock
    insuffisant) — à l'appelant (vue checkout) de l'attraper et d'afficher un
    message clair pour CETTE ligne précise, jamais un rejet global opaque."""
    products = fb_read.get_public_products_by_ids(shop_id, list(cart.keys()))
    lines = []
    for product_id, qty in cart.items():
        product = products.get(product_id)
        if product is None:
            raise CartLineError(product_id, product_id, 'unavailable')
        available = product['stockQty']
        if qty > available:
            raise CartLineError(product_id, product['name'], 'insufficient_stock', available)
        lines.append({
            'productId': product_id,
            'name': product['name'],
            'price': product['price'],
            'qty': qty,
        })
    return lines


def create_order(shop_id: str, *, customer_name: str, customer_phone: str,
                  customer_address: str, lines: list[dict]) -> str:
    """Écrit `storeOrders/{orderId}` (mode cash_on_delivery uniquement en
    Phase 2, cf. design). Retourne l'id généré."""
    total = sum(line['price'] * line['qty'] for line in lines)
    db = fb.db()
    _, doc_ref = db.collection('storeOrders').add({
        'shopId': shop_id,
        'createdAt': fb.firestore.SERVER_TIMESTAMP,
        'status': 'pending',
        'customerName': customer_name,
        'customerPhone': customer_phone,
        'customerAddress': customer_address,
        'items': lines,
        'totalAmount': total,
        'paymentMode': 'cash_on_delivery',
        'paymentRef': None,
    })
    return doc_ref.id
