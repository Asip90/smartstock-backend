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
