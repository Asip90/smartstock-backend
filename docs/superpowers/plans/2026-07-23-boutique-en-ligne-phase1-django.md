# Boutique en ligne — Phase 1 (site public Django) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Construire le site public en lecture seule d'une boutique Compa
(vitrine + catalogue + fiche produit, contact WhatsApp uniquement) accessible
par sous-domaine `<slug>.compa.nouyon.site`, dans ce dépôt Django
(`smartstock-backend`). Spec complète côté produit :
`/home/jey/smart_stock/docs/superpowers/specs/2026-07-22-boutique-en-ligne-design.md`.
Plan complémentaire côté Flutter :
`/home/jey/smart_stock/docs/superpowers/plans/2026-07-23-boutique-en-ligne-phase1-flutter.md`
(paramètres, génération IA déclenchée depuis l'app, lien de partage).

**Architecture:** Nouvelle app Django `storefront`, purement **lecture seule**
sur Firestore (via `billing/firebase_service.py`, déjà en place). Un
middleware résout la boutique à partir du sous-domaine et bascule
`request.urlconf` vers `storefront.urls` — **`core/urls.py` n'est pas
modifié**. Un sérialiseur explicite (`storefront/firebase_read.py`) ne renvoie
jamais de champ sensible. La génération de texte IA est exposée comme un
nouvel endpoint **authentifié** sous `/api/` (dépôt existant `billing/`), pas
sous le sous-domaine public.

**Tech Stack:** Django 5.0.6, `firebase-admin` (déjà en place),
`django.test.TestCase` + `unittest.mock` (convention existante du dépôt),
Tailwind via CDN (comme la landing page existante), pas de nouvelle
dépendance à ajouter.

## Décision d'architecture — écart avec la spec initiale

La spec prévoyait que la génération IA des textes soit déclenchée par l'app
Flutter, qui appellerait Mistral/Gemini directement (réutilisant
`PerformanceAiService`/`ConfigService`). En explorant `smartstock-backend`, il
existe déjà un pattern IA **fonctionnel, testé et déployé** :
`billing/ai_service.py` + le modèle singleton `AIConfig` (provider, clé API,
température — pilotables depuis Jazzmin admin). Dupliquer un second chemin
d'appel IA côté client serait contraire à DRY et forcerait à redéployer une
clé API dans Firestore `config/api_keys` alors qu'une config déjà en
production existe côté Django. **Décision : la génération de texte pour la
boutique en ligne se fait côté Django**, via un nouvel endpoint authentifié
que l'app Flutter appelle (voir le plan Flutter complémentaire) — réutilise
`AIConfig.get_solo()` pour la clé/le provider, mais avec son propre prompt et
son propre format de sortie (pas de couplage avec `ai_service.py`, qui reste
dédié aux notifications).

## Écart supplémentaire — analytics et favoris hors scope de ce plan

Pour rester livrable dans une passe raisonnable, ce plan **exclut** :
- Le comptage réel de vues (`pageViews`/`uniqueVisitors`/`productViews`,
  collection `storefrontStats`) et l'onglet Statistiques de l'app — reportés à
  un incrément ultérieur. **"Produits populaires" utilise à la place un repli
  temporaire** : les produits les plus récemment ajoutés (`createdAt`
  décroissant), en attendant les vraies statistiques de vues.
- Les favoris (cœur sur les cartes produit) et l'entrée "Favoris" de la barre
  de navigation basse — un cœur non fonctionnel serait une fonctionnalité
  à moitié finie ; mieux vaut l'omettre que l'afficher inerte. Navigation
  basse réduite à **Accueil / Catégories / Contact / À propos**.
- Le carrousel hero à plusieurs bannières (déjà tranché en Phase 0 : une
  seule bannière).
- Les modes Panier et Paiement en ligne (Phases 2/3), donc pas de panier ni
  de bouton "Ajouter au panier" dans ce plan — seul le bouton WhatsApp.

Ces exclusions sont documentées ici pour que l'humain puisse les
reconsidérer ; ce ne sont pas des oublis.

## Global Constraints

- **Aucune donnée sensible exposée** : le sérialiseur public ne renvoie
  jamais `purchasePrice`, `ifu`, `rccm`, `ownerId`, quantité exacte de stock
  (seulement `inStock: bool`).
- **Rétro-compatibilité Firestore** : `isPublic` absent sur un document
  `produits` existant doit être traité comme `true` (jamais filtré côté
  requête Firestore — Firestore ne matche pas les champs absents avec
  `where('isPublic', '==', True)` ; le filtre doit se faire **en Python**
  après lecture).
- **Aucune modification de `firestore.rules`** — lecture exclusivement via
  compte de service (`firebase-admin`), jamais depuis le navigateur.
- **`core/urls.py` non modifié** — tout le routing du sous-domaine passe par
  le middleware + `request.urlconf`.
- Style de code du dépôt : vues fonctionnelles (pas de classes DRF
  `APIView`), `JsonResponse`, tests `django.test.TestCase` +
  `unittest.mock.patch`, docstrings en français.
- Palette : thème bleu Compa (`#1565C0` par défaut, `primaryColorHex`
  personnalisable par boutique), zéro violet/ombre marquée/emoji/dégradé.
- **Direction artistique impérative** : avant de considérer une tâche de
  template terminée, relire `/home/jey/Téléchargements/modelsite.jpg` (via
  l'outil de lecture d'image) et comparer visuellement la structure produite
  à cette référence (proportions, hiérarchie, densité) — seule la couleur
  change (bleu au lieu de violet).

---

### Task 1: App Django `storefront` — scaffolding + settings

**Files:**
- Create: `storefront/__init__.py`
- Create: `storefront/apps.py`
- Modify: `core/settings.py`

**Interfaces:**
- Produces: app Django `storefront` enregistrée, réglage
  `STOREFRONT_BASE_DOMAINS` (liste de domaines, ex.
  `['compa.nouyon.site', 'compa.site']`) lisible par les tâches suivantes via
  `django.conf.settings.STOREFRONT_BASE_DOMAINS`.

- [ ] **Step 1: Créer le module d'app**

`storefront/__init__.py` (vide) :

```python
```

`storefront/apps.py` :

```python
from django.apps import AppConfig


class StorefrontConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'storefront'
    verbose_name = 'Boutique en ligne'
```

- [ ] **Step 2: Enregistrer l'app et le réglage de domaines dans `core/settings.py`**

Dans `core/settings.py`, remplacer le bloc `INSTALLED_APPS` actuel :

```python
INSTALLED_APPS = [
    'jazzmin',
    'corsheaders',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'billing',
]
```

par :

```python
INSTALLED_APPS = [
    'jazzmin',
    'corsheaders',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'billing',
    'storefront',
]
```

Puis, après le bloc `CSRF_TRUSTED_ORIGINS` (juste après sa fermeture `]`),
ajouter :

```python

# Domaines sous lesquels les sites de boutique en ligne sont servis, par
# sous-domaine (<slug>.<domaine>). `compa.site` sera ajouté une fois acheté
# (cf. spec boutique en ligne) ; le DNS wildcard doit être configuré côté
# registrar pour chaque domaine listé ici — non automatisable depuis ce repo.
STOREFRONT_BASE_DOMAINS = [
    d for d in os.environ.get(
        'STOREFRONT_BASE_DOMAINS', 'compa.nouyon.site'
    ).split(',') if d
]
```

- [ ] **Step 3: Vérifier que Django démarre correctement**

Run: `python manage.py check`
Expected: `System check identified no issues (0 silenced).`

- [ ] **Step 4: Commit**

```bash
git add storefront/__init__.py storefront/apps.py core/settings.py
git commit -m "feat(storefront): scaffolding de l'app boutique en ligne"
```

---

### Task 2: `storefront/i18n.py` — dictionnaire de traduction léger

**Files:**
- Create: `storefront/i18n.py`
- Test: `storefront/tests_i18n.py`

**Interfaces:**
- Produces: `t(key: str, lang: str) -> str`. Consommé par les Tasks 5 et 6
  (vues et templates).

**Contexte** : ce dépôt n'a **aucune infrastructure i18n Django** (pas de
`.po`, pas de `USE_I18N`, tout le texte existant est en dur en français).
Construire la machinerie `gettext` complète serait disproportionné pour ~15
libellés fixes. On utilise un dictionnaire Python `STRINGS` plutôt que
`django.utils.translation`.

- [ ] **Step 1: Écrire les tests**

Créer `storefront/tests_i18n.py` :

```python
from django.test import TestCase

from storefront.i18n import t


class TranslationTests(TestCase):
    def test_fr_par_defaut_pour_langue_inconnue(self):
        self.assertEqual(t('shop_now', 'de'), t('shop_now', 'fr'))

    def test_en_renvoie_texte_different_du_fr(self):
        self.assertNotEqual(t('shop_now', 'fr'), t('shop_now', 'en'))

    def test_cle_inconnue_renvoie_la_cle_elle_meme(self):
        self.assertEqual(t('cle_qui_nexiste_pas', 'fr'), 'cle_qui_nexiste_pas')
```

- [ ] **Step 2: Lancer les tests pour vérifier qu'ils échouent**

Run: `python manage.py test storefront.tests_i18n`
Expected: FAIL — `storefront.i18n` n'existe pas.

- [ ] **Step 3: Implémenter**

Créer `storefront/i18n.py` :

```python
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
```

- [ ] **Step 4: Lancer les tests pour vérifier qu'ils passent**

Run: `python manage.py test storefront.tests_i18n`
Expected: PASS (3/3).

- [ ] **Step 5: Commit**

```bash
git add storefront/i18n.py storefront/tests_i18n.py
git commit -m "feat(storefront): dictionnaire de traduction léger fr/en"
```

---

### Task 3: `storefront/firebase_read.py` — lectures publiques + sérialiseur

**Files:**
- Create: `storefront/firebase_read.py`
- Test: `storefront/tests_firebase_read.py`

**Interfaces:**
- Consumes: `billing.firebase_service.db()` (déjà en place).
- Produces: `get_shop_by_slug(slug)`, `list_public_products(shop_id, search='')`,
  `get_public_product(shop_id, product_id)`, `list_categories(shop_id)`.
  Consommé par la Task 5 (vues).

**Point critique rétro-compatibilité** : ne JAMAIS filtrer `isPublic` dans la
requête Firestore elle-même (`where('isPublic', '==', True)` ignorerait tout
document où le champ est absent, cassant la rétro-compatibilité — un produit
créé avant cette feature doit rester visible). Le filtre `isPublic` se fait
uniquement **après lecture, en Python**, avec un défaut `True` si absent.

- [ ] **Step 1: Écrire les tests (fonctions pures, sans appel Firestore réel)**

Créer `storefront/tests_firebase_read.py` :

```python
from django.test import TestCase

from storefront.firebase_read import _serialize_product, _shop_is_pro, _slugify


class SlugifyTests(TestCase):
    def test_minuscules_et_tirets(self):
        self.assertEqual(_slugify('Robe Été 2026'), 'robe-t-2026')

    def test_nom_vide_renvoie_repli(self):
        self.assertEqual(_slugify(''), 'produit')
        self.assertEqual(_slugify(None), 'produit')


class SerializeProductTests(TestCase):
    def test_url_slug_combine_id_et_slug_du_nom(self):
        product = _serialize_product({'id': 'p1', 'name': 'Robe Été', 'price': 1000})
        self.assertEqual(product['url_slug'], 'p1-robe-t')

    def test_repli_imageUrl_si_images_absent(self):
        product = _serialize_product({
            'id': 'p1', 'name': 'Sac', 'price': 1000, 'imageUrl': 'https://x/a.jpg',
        })
        self.assertEqual(product['images'], ['https://x/a.jpg'])

    def test_images_prioritaire_sur_imageUrl(self):
        product = _serialize_product({
            'id': 'p1', 'name': 'Sac', 'price': 1000,
            'imageUrl': 'https://x/old.jpg', 'images': ['https://x/a.jpg', 'https://x/b.jpg'],
        })
        self.assertEqual(product['images'], ['https://x/a.jpg', 'https://x/b.jpg'])

    def test_discount_ignore_si_superieur_ou_egal_au_prix(self):
        product = _serialize_product({'id': 'p1', 'name': 'Sac', 'price': 1000, 'discountPrice': 1000})
        self.assertIsNone(product['discountPrice'])
        self.assertIsNone(product['discountPercent'])

    def test_discount_valide_calcule_le_pourcentage(self):
        product = _serialize_product({'id': 'p1', 'name': 'Sac', 'price': 1000, 'discountPrice': 800})
        self.assertEqual(product['discountPrice'], 800)
        self.assertEqual(product['discountPercent'], 20)

    def test_inStock_vrai_si_quantite_positive(self):
        product = _serialize_product({'id': 'p1', 'name': 'Sac', 'price': 1000, 'quantity': 3})
        self.assertTrue(product['inStock'])

    def test_inStock_faux_si_quantite_nulle_ou_absente(self):
        self.assertFalse(_serialize_product({'id': 'p1', 'name': 'Sac', 'price': 1000, 'quantity': 0})['inStock'])
        self.assertFalse(_serialize_product({'id': 'p1', 'name': 'Sac', 'price': 1000})['inStock'])

    def test_ne_renvoie_jamais_de_champ_sensible(self):
        product = _serialize_product({
            'id': 'p1', 'name': 'Sac', 'price': 1000,
            'purchasePrice': 400, 'ownerId': 'u1',
        })
        self.assertNotIn('purchasePrice', product)
        self.assertNotIn('ownerId', product)


class ShopIsProTests(TestCase):
    def test_sans_proUntil_nest_pas_pro(self):
        self.assertFalse(_shop_is_pro({}))

    def test_proUntil_futur_est_pro(self):
        import datetime
        future = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=30)
        self.assertTrue(_shop_is_pro({'proUntil': future}))

    def test_proUntil_passe_nest_pas_pro(self):
        import datetime
        past = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=1)
        self.assertFalse(_shop_is_pro({'proUntil': past}))
```

- [ ] **Step 2: Lancer les tests pour vérifier qu'ils échouent**

Run: `python manage.py test storefront.tests_firebase_read`
Expected: FAIL — `storefront.firebase_read` n'existe pas.

- [ ] **Step 3: Implémenter**

Créer `storefront/firebase_read.py` :

```python
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
```

- [ ] **Step 4: Lancer les tests pour vérifier qu'ils passent**

Run: `python manage.py test storefront.tests_firebase_read`
Expected: PASS (tous les tests). Ces tests n'appellent jamais Firestore
(les fonctions testées sont pures — `_slugify`/`_serialize_product`/
`_shop_is_pro` — les fonctions qui appellent réellement `fb.db()` ne sont
pas testées ici, cohérent avec l'absence de mock Firestore dans ce dépôt).

- [ ] **Step 5: Vérifier la compilation**

Run: `python manage.py check`
Expected: `System check identified no issues (0 silenced).`

- [ ] **Step 6: Commit**

```bash
git add storefront/firebase_read.py storefront/tests_firebase_read.py
git commit -m "feat(storefront): lectures Firestore publiques + sérialiseur sûr"
```

---

### Task 4: `storefront/middleware.py` — résolution du sous-domaine

**Files:**
- Create: `storefront/middleware.py`
- Test: `storefront/tests_middleware.py`
- Modify: `core/settings.py`

**Interfaces:**
- Consumes: `settings.STOREFRONT_BASE_DOMAINS` (Task 1).
- Produces: pose `request.storefront_slug` (`str | None`) et bascule
  `request.urlconf = 'storefront.urls'` quand l'hôte correspond à un
  sous-domaine de boutique. Consommé par la Task 5 (vues) via
  `request.storefront_slug`.

- [ ] **Step 1: Écrire les tests**

Créer `storefront/tests_middleware.py` :

```python
from django.test import RequestFactory, TestCase, override_settings

from storefront.middleware import SubdomainStorefrontMiddleware


def _get_response(request):
    request.seen = True
    return 'ok'


class SubdomainMiddlewareTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.middleware = SubdomainStorefrontMiddleware(_get_response)

    @override_settings(STOREFRONT_BASE_DOMAINS=['compa.nouyon.site'])
    def test_sous_domaine_de_boutique_pose_le_slug_et_bascule_urlconf(self):
        request = self.factory.get('/', HTTP_HOST='ma-boutique.compa.nouyon.site')
        self.middleware(request)
        self.assertEqual(request.storefront_slug, 'ma-boutique')
        self.assertEqual(request.urlconf, 'storefront.urls')

    @override_settings(STOREFRONT_BASE_DOMAINS=['compa.nouyon.site'])
    def test_domaine_principal_sans_sous_domaine_ne_bascule_rien(self):
        request = self.factory.get('/', HTTP_HOST='compa.nouyon.site')
        self.middleware(request)
        self.assertIsNone(getattr(request, 'storefront_slug', None))
        self.assertFalse(hasattr(request, 'urlconf'))

    @override_settings(STOREFRONT_BASE_DOMAINS=['compa.nouyon.site'])
    def test_www_nest_pas_traite_comme_un_slug_de_boutique(self):
        request = self.factory.get('/', HTTP_HOST='www.compa.nouyon.site')
        self.middleware(request)
        self.assertIsNone(getattr(request, 'storefront_slug', None))

    @override_settings(STOREFRONT_BASE_DOMAINS=['compa.nouyon.site'])
    def test_port_dans_le_host_est_ignore(self):
        request = self.factory.get('/', HTTP_HOST='ma-boutique.compa.nouyon.site:8000')
        self.middleware(request)
        self.assertEqual(request.storefront_slug, 'ma-boutique')

    @override_settings(STOREFRONT_BASE_DOMAINS=['compa.nouyon.site'])
    def test_domaine_totalement_different_ne_bascule_rien(self):
        request = self.factory.get('/', HTTP_HOST='autresite.example.com')
        self.middleware(request)
        self.assertIsNone(getattr(request, 'storefront_slug', None))

    @override_settings(STOREFRONT_BASE_DOMAINS=['compa.nouyon.site'])
    def test_appelle_bien_get_response(self):
        request = self.factory.get('/', HTTP_HOST='ma-boutique.compa.nouyon.site')
        result = self.middleware(request)
        self.assertEqual(result, 'ok')
        self.assertTrue(request.seen)
```

- [ ] **Step 2: Lancer les tests pour vérifier qu'ils échouent**

Run: `python manage.py test storefront.tests_middleware`
Expected: FAIL — `storefront.middleware` n'existe pas.

- [ ] **Step 3: Implémenter**

Créer `storefront/middleware.py` :

```python
"""Résout la boutique à partir du sous-domaine de la requête et bascule le
routing vers `storefront.urls` — `core/urls.py` n'est jamais modifié, le
domaine principal (landing/API) continue de résoudre normalement."""
from django.conf import settings


class SubdomainStorefrontMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        host = request.get_host().split(':')[0].lower()
        request.storefront_slug = None

        for base_domain in getattr(settings, 'STOREFRONT_BASE_DOMAINS', []):
            suffix = '.' + base_domain
            if host == base_domain or not host.endswith(suffix):
                continue
            label = host[: -len(suffix)]
            if label and label != 'www':
                request.storefront_slug = label
                request.urlconf = 'storefront.urls'
            break

        return self.get_response(request)
```

- [ ] **Step 4: Enregistrer le middleware dans `core/settings.py`**

Remplacer le bloc `MIDDLEWARE` actuel :

```python
MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]
```

par :

```python
MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'storefront.middleware.SubdomainStorefrontMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]
```

(Placé tôt, avant `SessionMiddleware`, car il ne dépend d'aucun autre
middleware et doit s'exécuter avant la résolution d'URL.)

- [ ] **Step 5: Lancer les tests pour vérifier qu'ils passent**

Run: `python manage.py test storefront.tests_middleware`
Expected: PASS (6/6).

- [ ] **Step 6: Vérifier que Django démarre toujours**

Run: `python manage.py check`
Expected: `System check identified no issues (0 silenced).`

- [ ] **Step 7: Commit**

```bash
git add storefront/middleware.py storefront/tests_middleware.py core/settings.py
git commit -m "feat(storefront): middleware de résolution du sous-domaine"
```

---

### Task 5: Vues publiques — accueil, fiche produit, sitemap, robots

**Files:**
- Create: `storefront/urls.py`
- Create: `storefront/views.py`

**Interfaces:**
- Consumes: `storefront.firebase_read.*` (Task 3), `storefront.i18n.t` (Task 2).
- Produces: routes Django (`storefront_home`, `storefront_product`,
  `storefront_sitemap`, `storefront_robots`), consommées par les templates de
  la Task 6 (via `{% url %}` si besoin) et par le middleware (Task 4, déjà
  câblé pour y rediriger `request.urlconf`).

Pas de test automatisé pour cette tâche (vues qui appellent Firestore en
direct via `firebase_read`, sans mock — cohérent avec l'absence de tests sur
les vues `billing/views.py` équivalentes dans ce dépôt, qui ne testent que
les fonctions pures/le client HTTP mocké, jamais Firestore lui-même).
Vérification par `python manage.py check` uniquement.

- [ ] **Step 1: Créer `storefront/urls.py`**

```python
from django.urls import path

from . import views

urlpatterns = [
    path('', views.home, name='storefront_home'),
    path('produit/<str:product_slug>', views.product_detail, name='storefront_product'),
    path('sitemap.xml', views.sitemap, name='storefront_sitemap'),
    path('robots.txt', views.robots, name='storefront_robots'),
]
```

- [ ] **Step 2: Créer `storefront/views.py`**

```python
"""Vues publiques du site vitrine — servies via `storefront.urls`, dispatché
par `SubdomainStorefrontMiddleware` (jamais par `core/urls.py`)."""
from django.core.paginator import Paginator
from django.http import Http404, HttpResponse
from django.shortcuts import render

from . import firebase_read as fb_read
from .i18n import STRINGS, t

PAGE_SIZE = 24


def _lang(request) -> str:
    lang = request.GET.get('lang') or request.COOKIES.get('storefront_lang') or 'fr'
    return lang if lang in ('fr', 'en') else 'fr'


def _strings(lang: str) -> dict:
    """Dict précalculé { clé: texte traduit } pour tout `STRINGS` — Django ne
    permet pas d'appeler une fonction avec un argument depuis un template
    (`{{ t('home') }}` n'existe pas), donc on résout tout à l'avance et le
    template accède par attribut (`{{ t.home }}`, syntaxe Django standard sur
    un dict)."""
    return {key: t(key, lang) for key in STRINGS}


def _load_shop_or_none(request):
    slug = getattr(request, 'storefront_slug', None)
    return fb_read.get_shop_by_slug(slug) if slug else None


def _unavailable(request, lang, status=404):
    return render(request, 'storefront/unavailable.html', {
        'lang': lang, 't': _strings(lang),
    }, status=status)


def home(request):
    lang = _lang(request)
    shop = _load_shop_or_none(request)
    if shop is None:
        raise Http404('Boutique introuvable')
    if not shop['storefrontEnabled'] or not shop['isPro']:
        return _unavailable(request, lang)

    query = request.GET.get('q', '').strip()
    products = fb_read.list_public_products(shop['id'], search=query)
    categories = fb_read.list_categories(shop['id'])
    deals = [p for p in products if p['discountPrice']][:8]
    # Repli temporaire pour "populaires" en attendant les vraies statistiques
    # de vues (cf. plan, section "Écart supplémentaire").
    popular = sorted(products, key=lambda p: p['createdAt'] or 0, reverse=True)[:8]

    paginator = Paginator(products, PAGE_SIZE)
    page = paginator.get_page(request.GET.get('page') or 1)

    response = render(request, 'storefront/home.html', {
        'shop': shop, 'lang': lang, 't': _strings(lang),
        'categories': categories, 'deals': deals, 'popular': popular,
        'page': page, 'query': query,
    })
    response.set_cookie('storefront_lang', lang, max_age=60 * 60 * 24 * 365)
    return response


def product_detail(request, product_slug: str):
    lang = _lang(request)
    shop = _load_shop_or_none(request)
    if shop is None:
        raise Http404('Boutique introuvable')
    if not shop['storefrontEnabled'] or not shop['isPro']:
        return _unavailable(request, lang)

    product_id = product_slug.split('-', 1)[0]
    product = fb_read.get_public_product(shop['id'], product_id)
    if product is None:
        return render(request, 'storefront/product_not_found.html', {
            'shop': shop, 'lang': lang, 't': _strings(lang),
        }, status=404)

    return render(request, 'storefront/product_detail.html', {
        'shop': shop, 'product': product, 'lang': lang, 't': _strings(lang),
    })


def sitemap(request):
    shop = _load_shop_or_none(request)
    if shop is None or not shop['storefrontEnabled']:
        raise Http404('Boutique introuvable')

    base = f'https://{request.get_host()}'
    products = fb_read.list_public_products(shop['id'])
    urls = [base + '/'] + [f"{base}/produit/{p['url_slug']}" for p in products]
    body = '<?xml version="1.0" encoding="UTF-8"?>\n'
    body += '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    body += ''.join(f'<url><loc>{u}</loc></url>\n' for u in urls)
    body += '</urlset>'
    return HttpResponse(body, content_type='application/xml')


def robots(request):
    return HttpResponse(
        'User-agent: *\nAllow: /\nSitemap: /sitemap.xml\n',
        content_type='text/plain',
    )
```

- [ ] **Step 3: Vérifier**

Run: `python manage.py check`
Expected: `System check identified no issues (0 silenced).`

- [ ] **Step 4: Commit**

```bash
git add storefront/urls.py storefront/views.py
git commit -m "feat(storefront): vues publiques (accueil, fiche produit, sitemap, robots)"
```

---

### Task 6: Templates — structure fidèle à la maquette, thème bleu Compa

**Files:**
- Create: `templates/storefront/base.html`
- Create: `templates/storefront/home.html`
- Create: `templates/storefront/product_detail.html`
- Create: `templates/storefront/unavailable.html`
- Create: `templates/storefront/product_not_found.html`

**Interfaces:**
- Consumes: contexte fourni par les vues de la Task 5 (`shop`, `t`, `lang`,
  `categories`, `deals`, `popular`, `page`, `query`, `product`).

**Avant de commencer** : lire l'image `/home/jey/Téléchargements/modelsite.jpg`
(outil de lecture d'image) pour avoir la référence de structure sous les
yeux — header/recherche/hero/catégories en cercles/"Deals of the day"/
"Popular Products"/cartes produit. **Avant de considérer cette tâche
terminée**, relire l'image une seconde fois et comparer visuellement le
rendu produit (structure HTML, pas nécessairement un screenshot — raisonner
sur la disposition des éléments) à cette référence, en gardant seulement le
bleu Compa (`shop.primaryColorHex`, défaut `#1565C0`) à la place du violet.
Documenter cette comparaison dans le rapport.

- [ ] **Step 1: `templates/storefront/base.html`**

```html
<!DOCTYPE html>
<html lang="{{ lang }}">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{% block title %}{{ shop.name }}{% endblock %}</title>
    {% block meta %}
    <meta name="description" content="{{ shop.seoDescription_fr|default:shop.name }}">
    {% endblock %}
    <script src="https://cdn.tailwindcss.com"></script>
    <script>
        tailwind.config = {
            theme: {
                extend: {
                    colors: {
                        shopPrimary: '{{ shop.primaryColorHex|default:"#1565C0" }}',
                    },
                    fontFamily: { sans: ['Poppins', 'sans-serif'] },
                },
            },
        };
    </script>
    <link href="https://fonts.googleapis.com/css2?family=Poppins:wght@400;600;700;800&display=swap" rel="stylesheet">
</head>
<body class="font-sans bg-white text-gray-900">
    <header class="sticky top-0 z-10 bg-white border-b border-gray-100 px-4 py-3">
        <div class="max-w-5xl mx-auto flex items-center justify-between">
            <span class="font-extrabold text-lg tracking-tight">{{ shop.name }}</span>
            <nav class="flex items-center gap-4 text-sm font-semibold">
                <a href="{% url 'storefront_home' %}" class="text-shopPrimary">{{ t.home|default:"" }}</a>
            </nav>
        </div>
    </header>

    <main>{% block content %}{% endblock %}</main>

    <nav class="fixed bottom-0 inset-x-0 bg-white border-t border-gray-100 flex justify-around py-2 text-xs font-semibold text-gray-500">
        <a href="{% url 'storefront_home' %}" class="flex flex-col items-center gap-1 text-shopPrimary">
            <span>&#8962;</span><span>{{ t.home|default:"" }}</span>
        </a>
        <a href="{% url 'storefront_home' %}#categories" class="flex flex-col items-center gap-1">
            <span>&#9635;</span><span>{{ t.categories|default:"" }}</span>
        </a>
        {% if shop.allowContact %}
        <a href="https://wa.me/{{ shop.whatsappNumber }}" class="flex flex-col items-center gap-1">
            <span>&#9742;</span><span>{{ t.contact|default:"" }}</span>
        </a>
        {% endif %}
        <a href="#about" class="flex flex-col items-center gap-1">
            <span>&#8505;</span><span>{{ t.about|default:"" }}</span>
        </a>
    </nav>
    <div class="h-16"></div>
</body>
</html>
```

`t` est le dict précalculé `{clé: texte traduit}` construit par
`_strings(lang)` (Task 5) — accès par attribut Django standard sur un dict
(`{{ t.home }}`), jamais un appel de fonction (`{{ t('home') }}` n'existe pas
en syntaxe Django).

- [ ] **Step 2: `templates/storefront/home.html`**

```html
{% extends 'storefront/base.html' %}

{% block content %}
<div class="max-w-5xl mx-auto px-4 py-4">
    <form method="get" class="relative mb-6">
        <input type="text" name="q" value="{{ query }}" placeholder="{{ t.search_placeholder }}"
               class="w-full rounded-full border border-gray-200 py-3 px-5 text-sm focus:outline-none focus:border-shopPrimary">
    </form>

    {% if shop.heroImageUrl or shop.heroTitle_fr %}
    <section class="rounded-3xl bg-shopPrimary/10 p-8 mb-8 flex items-center justify-between overflow-hidden">
        <div class="max-w-xs">
            <h1 class="text-2xl md:text-3xl font-extrabold tracking-tight text-gray-900">
                {% if lang == 'en' %}{{ shop.heroTitle_en|default:shop.heroTitle_fr }}{% else %}{{ shop.heroTitle_fr }}{% endif %}
            </h1>
            <p class="mt-2 text-sm text-gray-600">
                {% if lang == 'en' %}{{ shop.heroSubtitle_en|default:shop.heroSubtitle_fr }}{% else %}{{ shop.heroSubtitle_fr }}{% endif %}
            </p>
            <a href="#catalog" class="inline-block mt-4 bg-shopPrimary text-white font-semibold rounded-full px-6 py-3 text-sm">
                {{ t.shop_now }}
            </a>
        </div>
        {% if shop.heroImageUrl %}
        <img src="{{ shop.heroImageUrl }}" alt="" class="w-32 h-32 object-cover rounded-2xl hidden md:block">
        {% endif %}
    </section>
    {% endif %}

    {% if categories %}
    <section id="categories" class="flex gap-4 overflow-x-auto mb-8 pb-2">
        {% for cat in categories %}
        <div class="flex flex-col items-center gap-2 shrink-0">
            <div class="w-14 h-14 rounded-full bg-shopPrimary/10 flex items-center justify-center">
                <span class="text-shopPrimary">&#9679;</span>
            </div>
            <span class="text-xs font-semibold">{{ cat.name }}</span>
        </div>
        {% endfor %}
    </section>
    {% endif %}

    {% if deals %}
    <section class="mb-8">
        <div class="flex justify-between items-center mb-3">
            <h2 class="font-bold text-lg">{{ t.deals_of_the_day }}</h2>
            <a href="?q=" class="text-shopPrimary text-sm font-semibold">{{ t.view_all }} &rarr;</a>
        </div>
        <div class="flex gap-4 overflow-x-auto pb-2">
            {% for p in deals %}
            <a href="{% url 'storefront_product' p.url_slug %}" class="shrink-0 w-40 border border-gray-100 rounded-2xl p-3">
                {% if p.images %}<img src="{{ p.images.0 }}" alt="{{ p.name }}" class="w-full h-28 object-cover rounded-xl mb-2">{% endif %}
                <p class="text-sm font-semibold truncate">{{ p.name }}</p>
                <p class="text-shopPrimary font-bold">{{ p.discountPrice }} {{ shop.currency }}</p>
                <p class="text-xs text-gray-400 line-through">{{ p.price }} {{ shop.currency }}</p>
                <span class="inline-block mt-1 text-[10px] font-bold bg-red-50 text-red-600 rounded-full px-2 py-0.5">
                    -{{ p.discountPercent }}%
                </span>
            </a>
            {% endfor %}
        </div>
    </section>
    {% endif %}

    {% if popular %}
    <section class="mb-8">
        <div class="flex justify-between items-center mb-3">
            <h2 class="font-bold text-lg">{{ t.popular_products }}</h2>
            <a href="?q=" class="text-shopPrimary text-sm font-semibold">{{ t.view_all }} &rarr;</a>
        </div>
        <div class="grid grid-cols-2 gap-4">
            {% for p in popular %}
            <a href="{% url 'storefront_product' p.url_slug %}" class="border border-gray-100 rounded-2xl p-3">
                {% if p.images %}<img src="{{ p.images.0 }}" alt="{{ p.name }}" class="w-full h-32 object-cover rounded-xl mb-2">{% endif %}
                <p class="text-sm font-semibold truncate">{{ p.name }}</p>
                <p class="text-shopPrimary font-bold">{{ p.price }} {{ shop.currency }}</p>
            </a>
            {% endfor %}
        </div>
    </section>
    {% endif %}

    <section id="catalog">
        {% if page.object_list %}
        <div class="grid grid-cols-2 gap-4">
            {% for p in page %}
            <a href="{% url 'storefront_product' p.url_slug %}" class="border border-gray-100 rounded-2xl p-3">
                {% if p.images %}<img src="{{ p.images.0 }}" alt="{{ p.name }}" class="w-full h-32 object-cover rounded-xl mb-2">{% endif %}
                <p class="text-sm font-semibold truncate">{{ p.name }}</p>
                <p class="text-shopPrimary font-bold">{{ p.price }} {{ shop.currency }}</p>
                {% if not p.inStock %}<p class="text-xs text-red-500">{{ t.out_of_stock }}</p>{% endif %}
            </a>
            {% endfor %}
        </div>
        {% if page.has_other_pages %}
        <div class="flex justify-center gap-2 mt-6 text-sm">
            {% if page.has_previous %}<a href="?page={{ page.previous_page_number }}&q={{ query }}" class="px-3 py-1 border rounded-full">&laquo;</a>{% endif %}
            {% if page.has_next %}<a href="?page={{ page.next_page_number }}&q={{ query }}" class="px-3 py-1 border rounded-full">&raquo;</a>{% endif %}
        </div>
        {% endif %}
        {% else %}
        <div class="text-center py-16">
            <p class="font-bold text-lg">{{ t.empty_catalog_title }}</p>
            <p class="text-sm text-gray-500 mt-1">{{ t.empty_catalog_subtitle }}</p>
        </div>
        {% endif %}
    </section>
</div>
{% endblock %}
```

Le lien produit utilise `p.url_slug` (déjà précalculé par
`_serialize_product`, Task 3 — `"<id>-<slug-du-nom>"`), jamais de
concaténation de filtres dans le tag `{% url %}` (Django ne le permet pas
proprement).

- [ ] **Step 3: `templates/storefront/product_detail.html`**

```html
{% extends 'storefront/base.html' %}

{% block title %}{{ product.name }} | {{ shop.name }}{% endblock %}
{% block meta %}
<meta property="og:title" content="{{ product.name }}">
<meta property="og:description" content="{{ product.description|truncatechars:160 }}">
{% if product.images %}<meta property="og:image" content="{{ product.images.0 }}">{% endif %}
<meta name="description" content="{{ product.description|truncatechars:160 }}">
{% endblock %}

{% block content %}
<div class="max-w-2xl mx-auto px-4 py-6">
    <a href="{% url 'storefront_home' %}" class="text-sm font-semibold text-shopPrimary">&larr; {{ t.back_to_shop }}</a>

    {% if product.images %}
    <div class="flex gap-3 overflow-x-auto mt-4 mb-4">
        {% for img in product.images %}
        <img src="{{ img }}" alt="{{ product.name }}" class="w-full max-w-md rounded-2xl object-cover shrink-0">
        {% endfor %}
    </div>
    {% endif %}
    {% if product.videoUrl %}
    <video controls class="w-full rounded-2xl mb-4"><source src="{{ product.videoUrl }}"></video>
    {% endif %}

    <h1 class="text-2xl font-extrabold">{{ product.name }}</h1>
    <div class="mt-2 flex items-center gap-3">
        <span class="text-xl font-bold text-shopPrimary">
            {{ product.discountPrice|default:product.price }} {{ shop.currency }}
        </span>
        {% if product.discountPrice %}
        <span class="text-sm text-gray-400 line-through">{{ product.price }} {{ shop.currency }}</span>
        <span class="text-xs font-bold bg-red-50 text-red-600 rounded-full px-2 py-0.5">-{{ product.discountPercent }}%</span>
        {% endif %}
    </div>
    <p class="mt-1 text-sm {% if product.inStock %}text-green-600{% else %}text-red-500{% endif %}">
        {% if product.inStock %}{{ t.in_stock }}{% else %}{{ t.out_of_stock }}{% endif %}
    </p>
    <p class="mt-4 text-gray-600 leading-relaxed">{{ product.description }}</p>

    {% if shop.allowContact %}
    <a href="https://wa.me/{{ shop.whatsappNumber }}?text={{ product.name|urlencode }}"
       class="mt-6 inline-block bg-shopPrimary text-white font-semibold rounded-full px-6 py-3 text-sm">
        {{ t.contact_whatsapp }}
    </a>
    {% endif %}
</div>
{% endblock %}
```

- [ ] **Step 4: `templates/storefront/unavailable.html`**

```html
{% extends 'storefront/base.html' %}
{% block content %}
<div class="max-w-md mx-auto px-4 py-24 text-center">
    <p class="font-bold text-xl">{{ t.unavailable_title }}</p>
</div>
{% endblock %}
```

- [ ] **Step 5: `templates/storefront/product_not_found.html`**

```html
{% extends 'storefront/base.html' %}
{% block content %}
<div class="max-w-md mx-auto px-4 py-24 text-center">
    <p class="font-bold text-xl">{{ t.product_not_found }}</p>
    <a href="{% url 'storefront_home' %}" class="mt-4 inline-block text-shopPrimary font-semibold">{{ t.back_to_shop }}</a>
</div>
{% endblock %}
```

- [ ] **Step 6: Relire la maquette de référence et comparer**

Relire `/home/jey/Téléchargements/modelsite.jpg` et comparer point par point
à la structure produite (header/recherche/hero/catégories/deals/populaires/
grille produits/nav basse) — documenter dans le rapport les correspondances
et les écarts assumés (une seule bannière, pas de cloche/favoris, cf. plan).

- [ ] **Step 7: Vérifier**

Run: `python manage.py check`
Expected: `System check identified no issues (0 silenced).`

Run: `python manage.py test storefront`
Expected: tous les tests des Tasks 2-4 toujours au vert (aucune régression).

- [ ] **Step 8: Commit**

```bash
git add templates/storefront/
git commit -m "feat(storefront): templates du site public (structure Shopmore, thème bleu Compa)"
```

---

### Task 7: Endpoint IA authentifié — génération des textes de section

**Files:**
- Create: `billing/storefront_ai_service.py`
- Create: `billing/storefront_ai_views.py`
- Test: `billing/tests_storefront_ai_service.py`
- Modify: `billing/urls.py`

**Interfaces:**
- Consumes: `billing.models.AIConfig` (existant), `billing.views._auth`/`_body`
  (pattern existant, à répliquer localement — ces helpers sont privés au
  module `billing/views.py`, donc réimplémentés à l'identique ici plutôt
  qu'importés, pour ne pas créer de dépendance fragile sur des noms privés
  d'un autre module).
- Produces: route `POST /api/shop/generate-storefront-content`. Consommé par
  le plan Flutter complémentaire (`online_shop_api.dart`).

- [ ] **Step 1: Écrire les tests**

Créer `billing/tests_storefront_ai_service.py` :

```python
from unittest.mock import Mock, patch

from django.test import TestCase

from billing.models import AIConfig
from billing.storefront_ai_service import generate_storefront_content


def _enable_config(**overrides):
    cfg = AIConfig.get_solo()
    cfg.enabled = True
    cfg.api_key = 'test-api-key'
    cfg.provider = 'mistral'
    cfg.model = 'mistral-small-latest'
    for key, value in overrides.items():
        setattr(cfg, key, value)
    cfg.save()
    return cfg


def _mock_response(payload: str):
    resp = Mock()
    resp.raise_for_status = Mock()
    resp.json.return_value = {'choices': [{'message': {'content': payload}}]}
    return resp


class GenerateStorefrontContentTests(TestCase):
    @patch('billing.storefront_ai_service.requests.post')
    def test_retourne_none_si_ia_desactivee(self, mock_post):
        AIConfig.get_solo()  # enabled=False par défaut
        result = generate_storefront_content(
            shop_name='Ma Boutique', shop_description='Vêtements pour tous',
            products=[], location='Cotonou',
        )
        self.assertIsNone(result)
        mock_post.assert_not_called()

    @patch('billing.storefront_ai_service.requests.post')
    def test_happy_path_parse_le_json_bilingue(self, mock_post):
        _enable_config()
        payload = (
            '{"heroTitle_fr": "Le style à petit prix", "heroTitle_en": "Style on a budget", '
            '"heroSubtitle_fr": "Vêtements et accessoires à Cotonou", "heroSubtitle_en": "Clothes and accessories in Cotonou", '
            '"aboutText_fr": "Boutique familiale depuis 2020.", "aboutText_en": "Family shop since 2020.", '
            '"seoDescription_fr": "Vêtements tendance à Cotonou.", "seoDescription_en": "Trendy clothes in Cotonou."}'
        )
        mock_post.return_value = _mock_response(payload)
        result = generate_storefront_content(
            shop_name='Ma Boutique', shop_description='Vêtements pour tous',
            products=[{'name': 'Robe', 'description': 'Robe légère', 'category': 'Vêtements'}],
            location='Cotonou',
        )
        self.assertEqual(result['heroTitle_fr'], 'Le style à petit prix')
        self.assertEqual(result['heroTitle_en'], 'Style on a budget')
        self.assertIn('aboutText_en', result)
        mock_post.assert_called_once()

    @patch('billing.storefront_ai_service.requests.post')
    def test_reponse_json_invalide_renvoie_none(self, mock_post):
        _enable_config()
        mock_post.return_value = _mock_response('ceci nest pas du json')
        result = generate_storefront_content(
            shop_name='Ma Boutique', shop_description='', products=[], location='',
        )
        self.assertIsNone(result)

    @patch('billing.storefront_ai_service.requests.post')
    def test_exception_reseau_renvoie_none_sans_lever(self, mock_post):
        _enable_config()
        mock_post.side_effect = Exception('timeout')
        result = generate_storefront_content(
            shop_name='Ma Boutique', shop_description='', products=[], location='',
        )
        self.assertIsNone(result)

    @patch('billing.storefront_ai_service.requests.post')
    def test_echantillon_produits_limite_a_20(self, mock_post):
        _enable_config()
        payload = (
            '{"heroTitle_fr": "x", "heroTitle_en": "x", "heroSubtitle_fr": "x", '
            '"heroSubtitle_en": "x", "aboutText_fr": "x", "aboutText_en": "x", '
            '"seoDescription_fr": "x", "seoDescription_en": "x"}'
        )
        mock_post.return_value = _mock_response(payload)
        many_products = [{'name': f'P{i}', 'description': '', 'category': ''} for i in range(50)]
        generate_storefront_content(
            shop_name='Ma Boutique', shop_description='', products=many_products, location='',
        )
        sent_body = mock_post.call_args.kwargs['json']
        user_message = sent_body['messages'][1]['content']
        # Au plus 20 produits mentionnés dans le prompt envoyé au modèle.
        self.assertLessEqual(user_message.count('P4'), 1)  # présence bornée, pas de vérif exhaustive
```

- [ ] **Step 2: Lancer les tests pour vérifier qu'ils échouent**

Run: `python manage.py test billing.tests_storefront_ai_service`
Expected: FAIL — `billing.storefront_ai_service` n'existe pas.

- [ ] **Step 3: Implémenter `billing/storefront_ai_service.py`**

```python
"""Génération des textes de section (hero/à propos/SEO) de la boutique en
ligne, en français ET en anglais, à partir des données réelles de la
boutique. Réutilise la config IA existante (`AIConfig`, déjà pilotée depuis
Jazzmin pour les notifications) mais avec son propre prompt — jamais couplé
à `ai_service.py`, qui reste dédié aux notifications."""
import json

import requests

from .models import AIConfig

_MAX_PRODUCTS_SAMPLE = 20

_SYSTEM_PROMPT = (
    "Tu rédiges le contenu d'un site vitrine e-commerce pour une boutique "
    "en Afrique de l'Ouest. Génère les textes en FRANÇAIS ET EN ANGLAIS, ton "
    "commercial mais sobre, orienté référencement local (ville/quartier si "
    "fourni), sans emphase excessive, sans emoji. Réponds STRICTEMENT en "
    "JSON avec exactement les clés suivantes, toutes des chaînes non vides : "
    "heroTitle_fr, heroTitle_en, heroSubtitle_fr, heroSubtitle_en, "
    "aboutText_fr, aboutText_en, seoDescription_fr, seoDescription_en."
)

_REQUIRED_KEYS = (
    'heroTitle_fr', 'heroTitle_en', 'heroSubtitle_fr', 'heroSubtitle_en',
    'aboutText_fr', 'aboutText_en', 'seoDescription_fr', 'seoDescription_en',
)


def _endpoint(provider: str) -> str | None:
    if provider == 'mistral':
        return 'https://api.mistral.ai/v1/chat/completions'
    if provider == 'openrouter':
        return 'https://openrouter.ai/api/v1/chat/completions'
    return None


def _build_user_message(shop_name, shop_description, products, location) -> str:
    lines = [f'Nom de la boutique : {shop_name}']
    if location:
        lines.append(f'Localisation : {location}')
    if shop_description:
        lines.append(f'Description : {shop_description}')
    sample = products[:_MAX_PRODUCTS_SAMPLE]
    if sample:
        lines.append('Échantillon de produits :')
        for p in sample:
            lines.append(f"- {p.get('name', '')} ({p.get('category', '')}) : {p.get('description', '')}")
    return '\n'.join(lines)


def generate_storefront_content(
    *, shop_name: str, shop_description: str, products: list[dict], location: str,
) -> dict | None:
    """Renvoie un dict avec les 8 clés bilingues, ou None si l'IA est
    désactivée/mal configurée/indisponible (jamais d'exception)."""
    cfg = AIConfig.get_solo()
    if not cfg.enabled or not cfg.api_key:
        return None

    url = _endpoint(cfg.provider)
    if url is None:
        return None

    try:
        resp = requests.post(
            url,
            json={
                'model': cfg.model,
                'messages': [
                    {'role': 'system', 'content': _SYSTEM_PROMPT},
                    {'role': 'user', 'content': _build_user_message(
                        shop_name, shop_description, products, location)},
                ],
                'temperature': 0.7,
                'max_tokens': 600,
                'response_format': {'type': 'json_object'},
            },
            headers={
                'Authorization': f'Bearer {cfg.api_key}',
                'Content-Type': 'application/json',
            },
            timeout=20,
        )
        resp.raise_for_status()
        content = resp.json()['choices'][0]['message']['content']
        data = json.loads(content)
        if not all(key in data for key in _REQUIRED_KEYS):
            return None
        return {key: data[key] for key in _REQUIRED_KEYS}
    except Exception:
        return None
```

- [ ] **Step 4: Lancer les tests pour vérifier qu'ils passent**

Run: `python manage.py test billing.tests_storefront_ai_service`
Expected: PASS (5/5).

- [ ] **Step 5: Créer `billing/storefront_ai_views.py`**

```python
"""Endpoint authentifié (Bearer Firebase) appelé par l'app Flutter quand le
propriétaire clique « Activer ma boutique » ou « Régénérer avec l'IA »."""
import json

from django.http import HttpResponseBadRequest, JsonResponse
from django.views.decorators.csrf import csrf_exempt

from . import firebase_service as fb
from .storefront_ai_service import generate_storefront_content


def _auth(request):
    header = request.headers.get('Authorization', '')
    if not header.startswith('Bearer '):
        return None, None
    try:
        return fb.verify_token(header.split(' ', 1)[1])
    except Exception:
        return None, None


def _body(request):
    try:
        return json.loads(request.body or b'{}')
    except Exception:
        return {}


@csrf_exempt
def generate_storefront_content_view(request):
    if request.method != 'POST':
        return HttpResponseBadRequest('POST requis')

    uid, _ = _auth(request)
    if not uid:
        return JsonResponse({'error': 'unauthorized'}, status=401)

    data = _body(request)
    shop_name = (data.get('shopName') or '').strip()
    if not shop_name:
        return JsonResponse({'error': 'shopName_requis'}, status=400)

    result = generate_storefront_content(
        shop_name=shop_name,
        shop_description=data.get('shopDescription') or '',
        products=data.get('products') or [],
        location=data.get('location') or '',
    )
    if result is None:
        return JsonResponse({'error': 'generation_indisponible'}, status=503)
    return JsonResponse(result)
```

- [ ] **Step 6: Enregistrer la route dans `billing/urls.py`**

Remplacer le contenu actuel :

```python
from django.urls import path
from . import views
from . import promoter_api

urlpatterns = [
    path('signup', views.signup),
    path('apply-promo', views.apply_promo),
    path('subscribe', views.subscribe),
    path('confirm', views.confirm),
    path('webhook/fedapay', views.webhook),
    path('me', views.me),
    path('crash', views.crash),
    path('notify-owner', views.notify_owner),
    path('promoter/me', promoter_api.promoter_me),
    path('promoter/code', promoter_api.promoter_create_code),
    path('promoter/dashboard', promoter_api.promoter_dashboard),
    path('promoter/withdraw', promoter_api.promoter_withdraw),
]
```

par :

```python
from django.urls import path
from . import views
from . import promoter_api
from . import storefront_ai_views

urlpatterns = [
    path('signup', views.signup),
    path('apply-promo', views.apply_promo),
    path('subscribe', views.subscribe),
    path('confirm', views.confirm),
    path('webhook/fedapay', views.webhook),
    path('me', views.me),
    path('crash', views.crash),
    path('notify-owner', views.notify_owner),
    path('promoter/me', promoter_api.promoter_me),
    path('promoter/code', promoter_api.promoter_create_code),
    path('promoter/dashboard', promoter_api.promoter_dashboard),
    path('promoter/withdraw', promoter_api.promoter_withdraw),
    path('shop/generate-storefront-content', storefront_ai_views.generate_storefront_content_view),
]
```

- [ ] **Step 7: Vérifier**

Run: `python manage.py check`
Expected: `System check identified no issues (0 silenced).`

Run: `python manage.py test billing.tests_storefront_ai_service storefront`
Expected: tous les tests au vert (aucune régression sur les Tasks
précédentes).

- [ ] **Step 8: Commit**

```bash
git add billing/storefront_ai_service.py billing/storefront_ai_views.py billing/tests_storefront_ai_service.py billing/urls.py
git commit -m "feat(billing): endpoint IA de génération des textes de la boutique en ligne"
```

---

## Prérequis infra restant (rappel — non automatisable depuis ce plan)

- **DNS wildcard** `*.compa.nouyon.site → IP du VPS` à créer côté registrar
  (action humaine, cf. spec section "Prérequis infra").
- Vérifier que `STOREFRONT_BASE_DOMAINS` et `ALLOWED_HOSTS` sont cohérents en
  prod (variable d'env Railway) une fois le DNS en place.
- Vérifier que la clé `AIConfig.api_key` déjà configurée pour les
  notifications a un quota suffisant pour absorber aussi les appels de
  génération de contenu boutique (même compte Mistral/OpenRouter) — sinon
  prévoir une clé/quota dédiés.
