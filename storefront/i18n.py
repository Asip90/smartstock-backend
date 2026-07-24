"""Dictionnaire de traduction léger pour le site public de la boutique en
ligne. Pas de machinerie gettext (aucune infra i18n Django dans ce dépôt) :
un simple dict clé -> {fr, en}, suffisant pour le chrome fixe de l'interface
(les données saisies par le propriétaire — noms produits/catégories — ne
sont, elles, jamais traduites, cf. spec)."""

STRINGS: dict[str, dict[str, str]] = {
    'search_placeholder': {'fr': 'Rechercher un produit…', 'en': 'Search for a product…'},
    'shop_now': {'fr': 'Voir les produits', 'en': 'Shop now'},
    'deals_of_the_day': {'fr': 'Offres du jour', 'en': 'Deals of the day'},
    'popular_products': {'fr': 'Produits populaires', 'en': 'Popular products'},
    'view_all': {'fr': 'Voir tout', 'en': 'View all'},
    'contact_whatsapp': {'fr': 'Contacter sur WhatsApp', 'en': 'Contact on WhatsApp'},
    'in_stock': {'fr': 'En stock', 'en': 'In stock'},
    'out_of_stock': {'fr': 'Rupture de stock', 'en': 'Out of stock'},
    'home': {'fr': 'Accueil', 'en': 'Home'},
    'categories': {'fr': 'Catégories', 'en': 'Categories'},
    'contact': {'fr': 'Contact', 'en': 'Contact'},
    'about': {'fr': 'À propos', 'en': 'About'},
    'empty_catalog_title': {
        'fr': 'Cette boutique prépare son catalogue',
        'en': 'This shop is preparing its catalog',
    },
    'empty_catalog_subtitle': {'fr': 'Revenez bientôt.', 'en': 'Check back soon.'},
    'unavailable_title': {
        'fr': "Cette boutique n'est plus disponible",
        'en': 'This shop is no longer available',
    },
    'product_not_found': {
        'fr': "Cet article n'est plus disponible",
        'en': 'This item is no longer available',
    },
    'back_to_shop': {'fr': 'Retour à la boutique', 'en': 'Back to the shop'},
    'off_badge': {'fr': '{percent}% de réduction', 'en': '{percent}% OFF'},
    'cart': {'fr': 'Panier', 'en': 'Cart'},
    'add_to_cart': {'fr': 'Ajouter au panier', 'en': 'Add to cart'},
    'added_to_cart': {'fr': 'Ajouté au panier', 'en': 'Added to cart'},
    'cart_empty': {'fr': 'Votre panier est vide', 'en': 'Your cart is empty'},
    'quantity': {'fr': 'Quantité', 'en': 'Quantity'},
    'remove': {'fr': 'Retirer', 'en': 'Remove'},
    'total': {'fr': 'Total', 'en': 'Total'},
    'checkout': {'fr': 'Passer la commande', 'en': 'Checkout'},
    'customer_name': {'fr': 'Nom complet', 'en': 'Full name'},
    'customer_phone': {'fr': 'Numéro de téléphone', 'en': 'Phone number'},
    'customer_address': {'fr': 'Adresse de livraison', 'en': 'Delivery address'},
    'payment_cash_on_delivery': {'fr': 'Paiement à la livraison', 'en': 'Cash on delivery'},
    'confirm_order': {'fr': 'Confirmer la commande', 'en': 'Confirm order'},
    'order_confirmed_title': {'fr': 'Commande envoyée !', 'en': 'Order sent!'},
    'order_confirmed_body': {
        'fr': 'Le vendeur va vous contacter pour confirmer la livraison.',
        'en': 'The seller will contact you to confirm delivery.',
    },
    'back_to_home': {'fr': "Retour à l'accueil", 'en': 'Back to home'},
    'stock_error_unavailable': {
        'fr': "« {name} » n'est plus disponible, retiré du panier.",
        'en': '"{name}" is no longer available, removed from cart.',
    },
    'stock_error_insufficient': {
        'fr': "Stock insuffisant pour « {name} » (il en reste {available}).",
        'en': 'Not enough stock for "{name}" ({available} left).',
    },
    'too_many_attempts': {
        'fr': 'Trop de tentatives, réessayez dans quelques minutes.',
        'en': 'Too many attempts, please try again in a few minutes.',
    },
    'pay_cash_on_delivery': {'fr': 'Paiement à la livraison', 'en': 'Cash on delivery'},
    'pay_online': {'fr': 'Payer en ligne maintenant', 'en': 'Pay online now'},
    'online_payment_email_label': {'fr': 'Email (reçu de paiement)', 'en': 'Email (payment receipt)'},
    'online_payment_email_required': {
        'fr': 'Un email est requis pour payer en ligne.',
        'en': 'An email is required to pay online.',
    },
    'online_payment_unavailable': {
        'fr': 'Paiement en ligne indisponible pour le moment, réessayez ou choisissez le paiement à la livraison.',
        'en': 'Online payment unavailable right now, try again or choose cash on delivery.',
    },
}

_DEFAULT_LANG = 'fr'
_SUPPORTED = ('fr', 'en')


def t(key: str, lang: str) -> str:
    """Traduit ``key`` dans ``lang`` (repli sur fr si lang/clé inconnus)."""
    entry = STRINGS.get(key)
    if entry is None:
        return key
    lang = lang if lang in _SUPPORTED else _DEFAULT_LANG
    return entry.get(lang, entry[_DEFAULT_LANG])
