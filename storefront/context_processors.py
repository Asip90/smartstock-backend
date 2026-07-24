"""Context processor exposant le nombre d'articles du panier à tous les
templates du site public (badge header/nav basse), sans devoir le repasser
dans le contexte de chaque vue."""
from . import cart as cart_mod


def cart_context(request):
    if not hasattr(request, 'session'):
        return {'cart_count': 0}
    return {'cart_count': cart_mod.cart_item_count(request)}
