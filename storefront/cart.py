"""Panier du site public — stocké en session Django (pas de compte client,
pas d'écriture Firestore avant validation du checkout). Clé de session
unique `cart`, dict `{product_id: qty}` : structure la plus simple possible,
un panier ne dépasse jamais quelques dizaines de lignes."""

_SESSION_KEY = 'cart'


def get_cart(request) -> dict[str, int]:
    """Contenu brut du panier (product_id -> quantité)."""
    return dict(request.session.get(_SESSION_KEY, {}))


def _save(request, cart: dict[str, int]) -> None:
    request.session[_SESSION_KEY] = cart
    request.session.modified = True


def add_to_cart(request, product_id: str, qty: int = 1) -> None:
    """Ajoute `qty` au produit (cumule si déjà présent)."""
    cart = get_cart(request)
    cart[product_id] = cart.get(product_id, 0) + qty
    _save(request, cart)


def set_quantity(request, product_id: str, qty: int) -> None:
    """Fixe la quantité exacte. `qty <= 0` retire la ligne (repli sûr côté
    UI : un client qui vide le champ quantité ne casse rien)."""
    cart = get_cart(request)
    if qty <= 0:
        cart.pop(product_id, None)
    else:
        cart[product_id] = qty
    _save(request, cart)


def remove_from_cart(request, product_id: str) -> None:
    cart = get_cart(request)
    cart.pop(product_id, None)
    _save(request, cart)


def clear_cart(request) -> None:
    _save(request, {})


def cart_item_count(request) -> int:
    """Nombre total d'articles (somme des quantités), pour le badge du
    panier dans le header/nav basse."""
    return sum(get_cart(request).values())
