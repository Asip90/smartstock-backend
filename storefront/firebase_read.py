"""Lectures Firestore PUBLIQUES, en LECTURE SEULE, pour le site vitrine.

Sérialiseur explicite : ne renvoie JAMAIS purchasePrice/ifu/rccm/ownerId ni
la quantité exacte de stock (seulement un booléen `inStock`). Le filtre de
visibilité `isPublic` se fait toujours EN PYTHON après lecture (jamais dans
la requête Firestore elle-même), pour ne pas exclure les produits créés
avant cette feature (champ absent = public, par rétro-compatibilité)."""
import datetime
import re

from billing import firebase_service as fb


def _slugify(name: str | None) -> str:
    """Slug cosmétique/SEO pour l'URL produit — l'id reste la clé canonique."""
    s = re.sub(r'[^a-z0-9]+', '-', (name or '').lower()).strip('-')
    return s or 'produit'


def _shop_is_pro(shop_data: dict) -> bool:
    """La boutique en ligne est réservée à l'abonnement Pro (cf. spec)."""
    pro_until = shop_data.get('proUntil')
    if not pro_until:
        return False
    try:
        return pro_until > datetime.datetime.now(datetime.timezone.utc)
    except TypeError:
        return False


def _serialize_product(data: dict) -> dict:
    """Transforme un document Firestore `produits` brut en dict public sûr."""
    images = data.get('images') or ([data['imageUrl']] if data.get('imageUrl') else [])
    price = data.get('price', 0) or 0
    raw_discount = data.get('discountPrice')
    discount = raw_discount if (raw_discount and raw_discount < price) else None
    slug = _slugify(data.get('name'))
    return {
        'id': data.get('id'),
        'name': data.get('name', ''),
        'slug': slug,
        # Segment d'URL prêt à l'emploi pour {% url 'storefront_product' %} —
        # évite toute concaténation de filtres dans les templates (Django ne
        # permet pas `{% url ... a|add:b %}` proprement).
        'url_slug': f"{data.get('id')}-{slug}",
        'description': data.get('description') or '',
        'price': price,
        'discountPrice': discount,
        'discountPercent': round((price - discount) / price * 100) if discount else None,
        'images': images,
        'videoUrl': data.get('videoUrl'),
        'categoryId': data.get('categoryId'),
        'inStock': (data.get('quantity') or 0) > 0,
        'createdAt': data.get('createdAt'),
    }


def get_shop_by_slug(slug: str) -> dict | None:
    """Boutique publique par sous-domaine, ou None si slug inconnu."""
    if not slug:
        return None
    db = fb.db()
    query = db.collection('shops').where('publicSlug', '==', slug).limit(1).stream()
    doc = next(query, None)
    if doc is None:
        return None
    data = doc.to_dict()
    settings_ = data.get('storefrontSettings') or {}
    return {
        'id': doc.id,
        'name': data.get('name', ''),
        'publicSlug': data.get('publicSlug'),
        'storefrontEnabled': bool(data.get('storefrontEnabled')),
        'currency': data.get('currency') or 'XOF',
        'heroImageUrl': settings_.get('heroImageUrl'),
        'heroTitle_fr': settings_.get('heroTitle_fr'),
        'heroTitle_en': settings_.get('heroTitle_en'),
        'heroSubtitle_fr': settings_.get('heroSubtitle_fr'),
        'heroSubtitle_en': settings_.get('heroSubtitle_en'),
        'aboutText_fr': settings_.get('aboutText_fr'),
        'aboutText_en': settings_.get('aboutText_en'),
        'seoDescription_fr': settings_.get('seoDescription_fr'),
        'seoDescription_en': settings_.get('seoDescription_en'),
        'whatsappNumber': settings_.get('whatsappNumber'),
        'allowContact': bool(settings_.get('allowContact', True)),
        'primaryColorHex': settings_.get('primaryColorHex') or '#1565C0',
        'isPro': _shop_is_pro(data),
    }


def list_public_products(shop_id: str, search: str = '') -> list[dict]:
    """Produits publics d'une boutique (isPublic filtré EN PYTHON, cf. docstring module)."""
    db = fb.db()
    docs = db.collection('produits').where('shopId', '==', shop_id).limit(800).stream()
    raw = [d.to_dict() | {'id': d.id} for d in docs if d.to_dict().get('isPublic', True)]
    products = [_serialize_product(d) for d in raw]
    if search:
        needle = search.strip().lower()
        products = [
            p for p in products
            if needle in p['name'].lower() or needle in p['description'].lower()
        ]
    return products


def get_public_product(shop_id: str, product_id: str) -> dict | None:
    """Une fiche produit publique, ou None si absente/privée/hors boutique."""
    db = fb.db()
    doc = db.collection('produits').document(product_id).get()
    if not doc.exists:
        return None
    data = doc.to_dict()
    if data.get('shopId') != shop_id or not data.get('isPublic', True):
        return None
    return _serialize_product(data | {'id': doc.id})


def list_categories(shop_id: str) -> list[dict]:
    """Catégories d'une boutique (nom + icône, pour la rangée de catégories)."""
    db = fb.db()
    docs = db.collection('categories').where('shopId', '==', shop_id).limit(100).stream()
    return [
        {'id': d.id, 'name': d.to_dict().get('name', ''), 'iconName': d.to_dict().get('iconName')}
        for d in docs
    ]
