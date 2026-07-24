# Boutique en ligne — Phase 2 (panier & commandes, site public Django) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ajouter au site public `storefront` un panier (session Django),
un checkout qui valide le stock réel avant de créer une commande
`storeOrders` (mode `cash_on_delivery` uniquement), une notification push au
propriétaire, et un throttle simple anti-spam sur la création de commande.

**Architecture:** Panier stocké dans `request.session` (clé `cart`, dict
`{productId: qty}`), jamais en base — cohérent avec "pas de compte client".
Le checkout relit les produits réels via `firebase_read` (déjà en place)
avant d'écrire `storeOrders` via l'Admin SDK (`billing.firebase_service`),
jamais une confiance aveugle aux prix/quantités envoyés par le navigateur.
Toute écriture (commande, notification) passe par le compte de service,
jamais par le client. Priorité expérience utilisateur : messages d'erreur
clairs par ligne de panier (jamais un rejet global opaque), panier qui
survit à la navigation, confirmation immédiate et lisible après commande.

**Tech Stack:** Django 5.0.6 (déjà en place), `django.contrib.sessions`
(déjà activé, `SessionMiddleware` dans `MIDDLEWARE`),
`django.contrib.messages` (déjà activé), `firebase-admin` (déjà en place,
`billing/firebase_service.py`), Tailwind CDN + Poppins (patterns déjà établis
dans `templates/storefront/base.html`), `django.test.TestCase` +
`unittest.mock.patch`.

## Global Constraints

- Style du dépôt : vues fonctionnelles (pas de classes DRF `APIView`),
  `JsonResponse` seulement pour les endpoints appelés en AJAX,
  `django.test.TestCase` + `unittest.mock.patch`, docstrings en français.
- Aucune dépendance nouvelle à ajouter (throttle et panier faits main, pas de
  `django-ratelimit`).
- `core/urls.py` n'est jamais modifié — tout nouveau routing public passe par
  `storefront/urls.py`, résolu par `SubdomainStorefrontMiddleware` déjà en
  place.
- `firestore.rules` n'est pas modifié — toute écriture Firestore passe par
  `billing.firebase_service` / `storefront.firebase_read` (compte de
  service), jamais depuis le navigateur.
- Sérialiseur public (`storefront/firebase_read.py`) : ne jamais exposer
  `purchasePrice`/`ifu`/`rccm`/`ownerId`/quantité exacte de stock au visiteur.
  Cette règle s'applique aussi au panier/checkout : le prix affiché et
  validé au checkout est toujours relu depuis Firestore, jamais accepté tel
  quel depuis un champ de formulaire caché.
- Mode de paiement en Phase 2 : `cash_on_delivery` uniquement (`paymentMode`
  toujours cette valeur, `paymentRef` toujours `null`) — décision figée dans
  `smart_stock/docs/superpowers/specs/2026-07-24-boutique-en-ligne-phase2-design.md`.
- Palette/thème : reprendre `shopPrimary` (`shop.primaryColorHex`) et
  `font-sans` (Poppins) déjà configurés dans `templates/storefront/base.html`
  — zéro violet/ombre marquée/emoji/dégradé, cohérent avec le reste du site.
- Chrome de l'interface (labels panier/checkout) : ajouter les clés dans
  `storefront/i18n.py` (`STRINGS`), jamais de texte en dur dans les
  templates — même mécanisme que les pages déjà livrées.

---

### Task 1: `storefront/cart.py` — panier en session (fonctions pures)

**Files:**
- Create: `storefront/cart.py`
- Test: `storefront/tests_cart.py`

**Interfaces:**
- Produces: `get_cart(request) -> dict[str, int]`,
  `add_to_cart(request, product_id: str, qty: int = 1) -> None`,
  `set_quantity(request, product_id: str, qty: int) -> None` (qty <= 0
  supprime la ligne), `remove_from_cart(request, product_id: str) -> None`,
  `clear_cart(request) -> None`, `cart_item_count(request) -> int`.
  Consommés par les Tasks 2 et 3.

- [ ] **Step 1: Écrire les tests (ils doivent échouer, le module n'existe pas)**

Créer `storefront/tests_cart.py` :

```python
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory, TestCase

from storefront import cart as cart_mod


def _request_with_session():
    request = RequestFactory().get('/')
    SessionMiddleware(lambda r: None).process_request(request)
    request.session.save()
    return request


class CartSessionTests(TestCase):
    def setUp(self):
        self.request = _request_with_session()

    def test_panier_vide_par_defaut(self):
        self.assertEqual(cart_mod.get_cart(self.request), {})
        self.assertEqual(cart_mod.cart_item_count(self.request), 0)

    def test_add_to_cart_cree_la_ligne(self):
        cart_mod.add_to_cart(self.request, 'p1', 2)
        self.assertEqual(cart_mod.get_cart(self.request), {'p1': 2})

    def test_add_to_cart_cumule_les_quantites(self):
        cart_mod.add_to_cart(self.request, 'p1', 2)
        cart_mod.add_to_cart(self.request, 'p1', 3)
        self.assertEqual(cart_mod.get_cart(self.request), {'p1': 5})

    def test_add_to_cart_qty_par_defaut_est_1(self):
        cart_mod.add_to_cart(self.request, 'p1')
        self.assertEqual(cart_mod.get_cart(self.request), {'p1': 1})

    def test_set_quantity_remplace_la_valeur(self):
        cart_mod.add_to_cart(self.request, 'p1', 5)
        cart_mod.set_quantity(self.request, 'p1', 2)
        self.assertEqual(cart_mod.get_cart(self.request), {'p1': 2})

    def test_set_quantity_zero_ou_negative_supprime_la_ligne(self):
        cart_mod.add_to_cart(self.request, 'p1', 5)
        cart_mod.set_quantity(self.request, 'p1', 0)
        self.assertEqual(cart_mod.get_cart(self.request), {})

    def test_remove_from_cart(self):
        cart_mod.add_to_cart(self.request, 'p1', 2)
        cart_mod.add_to_cart(self.request, 'p2', 1)
        cart_mod.remove_from_cart(self.request, 'p1')
        self.assertEqual(cart_mod.get_cart(self.request), {'p2': 1})

    def test_remove_from_cart_id_absent_ne_leve_pas(self):
        cart_mod.remove_from_cart(self.request, 'inconnu')
        self.assertEqual(cart_mod.get_cart(self.request), {})

    def test_clear_cart(self):
        cart_mod.add_to_cart(self.request, 'p1', 2)
        cart_mod.clear_cart(self.request)
        self.assertEqual(cart_mod.get_cart(self.request), {})

    def test_cart_item_count_somme_les_quantites(self):
        cart_mod.add_to_cart(self.request, 'p1', 2)
        cart_mod.add_to_cart(self.request, 'p2', 3)
        self.assertEqual(cart_mod.cart_item_count(self.request), 5)
```

- [ ] **Step 2: Lancer les tests pour vérifier qu'ils échouent**

Run: `python manage.py test storefront.tests_cart`
Expected: FAIL (import error, `storefront.cart` n'existe pas).

- [ ] **Step 3: Implémenter `storefront/cart.py`**

```python
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
```

- [ ] **Step 4: Lancer les tests pour vérifier qu'ils passent**

Run: `python manage.py test storefront.tests_cart`
Expected: PASS (10/10).

- [ ] **Step 5: Commit**

```bash
git add storefront/cart.py storefront/tests_cart.py
git commit -m "feat(storefront): panier en session (fonctions pures)"
```

---

### Task 2: `firebase_read.get_public_products_by_ids` + `get_shop_owner_uid`

**Files:**
- Modify: `storefront/firebase_read.py`
- Test: `storefront/tests_firebase_read.py`

**Interfaces:**
- Consumes: rien de nouveau (mêmes patterns que `list_public_products`).
- Produces: `get_public_products_by_ids(shop_id: str, product_ids: list[str]) -> dict[str, dict]`
  (map `product_id -> produit sérialisé`, absents omis — produit
  supprimé/privé entre-temps). `get_shop_owner_uid(shop_id: str) -> str | None`
  — lecture **interne** (jamais exposée au template public), utilisée
  uniquement pour router la notification push au bon propriétaire.
  Consommés par les Tasks 3 et 5.

- [ ] **Step 1: Écrire les tests**

Ajouter à `storefront/tests_firebase_read.py` (à la fin du fichier) :

```python
from unittest.mock import MagicMock, patch

from storefront.firebase_read import get_public_products_by_ids, get_shop_owner_uid


class GetPublicProductsByIdsTests(TestCase):
    @patch('storefront.firebase_read.fb.db')
    def test_renvoie_un_dict_id_vers_produit_serialise(self, mock_db):
        doc1 = MagicMock()
        doc1.exists = True
        doc1.id = 'p1'
        doc1.to_dict.return_value = {'shopId': 's1', 'name': 'Sac', 'price': 1000, 'isPublic': True}
        doc2 = MagicMock()
        doc2.exists = True
        doc2.id = 'p2'
        doc2.to_dict.return_value = {'shopId': 's1', 'name': 'Robe', 'price': 2000, 'isPublic': True}

        def get_doc(pid):
            m = MagicMock()
            m.get.return_value = {'p1': doc1, 'p2': doc2}[pid]
            return m

        mock_db.return_value.collection.return_value.document.side_effect = get_doc

        result = get_public_products_by_ids('s1', ['p1', 'p2'])
        self.assertEqual(set(result.keys()), {'p1', 'p2'})
        self.assertEqual(result['p1']['name'], 'Sac')

    @patch('storefront.firebase_read.fb.db')
    def test_omet_les_produits_absents_ou_prives(self, mock_db):
        missing = MagicMock()
        missing.exists = False
        private = MagicMock()
        private.exists = True
        private.id = 'p2'
        private.to_dict.return_value = {'shopId': 's1', 'name': 'X', 'price': 1, 'isPublic': False}

        def get_doc(pid):
            m = MagicMock()
            m.get.return_value = {'p1': missing, 'p2': private}[pid]
            return m

        mock_db.return_value.collection.return_value.document.side_effect = get_doc

        result = get_public_products_by_ids('s1', ['p1', 'p2'])
        self.assertEqual(result, {})

    @patch('storefront.firebase_read.fb.db')
    def test_omet_les_produits_d_une_autre_boutique(self, mock_db):
        doc = MagicMock()
        doc.exists = True
        doc.id = 'p1'
        doc.to_dict.return_value = {'shopId': 'autre-boutique', 'name': 'X', 'price': 1}
        mock_db.return_value.collection.return_value.document.return_value.get.return_value = doc

        result = get_public_products_by_ids('s1', ['p1'])
        self.assertEqual(result, {})


class GetShopOwnerUidTests(TestCase):
    @patch('storefront.firebase_read.fb.db')
    def test_renvoie_ownerId_du_document_boutique(self, mock_db):
        doc = MagicMock()
        doc.exists = True
        doc.to_dict.return_value = {'ownerId': 'u1'}
        mock_db.return_value.collection.return_value.document.return_value.get.return_value = doc

        self.assertEqual(get_shop_owner_uid('s1'), 'u1')

    @patch('storefront.firebase_read.fb.db')
    def test_renvoie_none_si_boutique_absente(self, mock_db):
        doc = MagicMock()
        doc.exists = False
        mock_db.return_value.collection.return_value.document.return_value.get.return_value = doc

        self.assertIsNone(get_shop_owner_uid('s1'))
```

- [ ] **Step 2: Lancer les tests pour vérifier qu'ils échouent**

Run: `python manage.py test storefront.tests_firebase_read.GetPublicProductsByIdsTests storefront.tests_firebase_read.GetShopOwnerUidTests`
Expected: FAIL (import error, les deux fonctions n'existent pas).

- [ ] **Step 3: Implémenter dans `storefront/firebase_read.py`**

Ajouter à la fin du fichier :

```python


def get_public_products_by_ids(shop_id: str, product_ids: list[str]) -> dict[str, dict]:
    """Relit les produits réels (prix, stock) pour une liste d'ids — utilisé
    par le panier/checkout pour ne JAMAIS faire confiance aux valeurs
    envoyées par le navigateur. Un id supprimé/privé/d'une autre boutique
    est silencieusement omis (le checkout traite ça comme une ligne de
    panier obsolète, cf. `storefront/orders.py`)."""
    db = fb.db()
    result: dict[str, dict] = {}
    for product_id in product_ids:
        doc = db.collection('produits').document(product_id).get()
        if not doc.exists:
            continue
        data = doc.to_dict()
        if data.get('shopId') != shop_id or not data.get('isPublic', True):
            continue
        result[product_id] = _serialize_product(data | {'id': doc.id})
    return result


def get_shop_owner_uid(shop_id: str) -> str | None:
    """Lecture INTERNE (jamais exposée au sérialiseur public
    `get_shop_by_slug`) : uid du propriétaire, utilisé uniquement pour
    router la notification push d'une nouvelle commande."""
    db = fb.db()
    doc = db.collection('shops').document(shop_id).get()
    if not doc.exists:
        return None
    return doc.to_dict().get('ownerId')
```

- [ ] **Step 4: Lancer les tests pour vérifier qu'ils passent**

Run: `python manage.py test storefront.tests_firebase_read`
Expected: PASS (toutes les classes, y compris les préexistantes — aucune
régression).

- [ ] **Step 5: Commit**

```bash
git add storefront/firebase_read.py storefront/tests_firebase_read.py
git commit -m "feat(storefront): lecture produits par ids + owner uid interne (préparation panier)"
```

---

### Task 3: `storefront/orders.py` — validation stock + création `storeOrders`

**Files:**
- Create: `storefront/orders.py`
- Test: `storefront/tests_orders.py`

**Interfaces:**
- Consumes: `get_public_products_by_ids` (Task 2).
- Produces: `class CartLineError` (exception, attributs `product_id: str`,
  `product_name: str`, `reason: str` — `'unavailable'` ou `'insufficient_stock'`,
  `available: int | None`) ; `build_order_lines(shop_id: str, cart: dict[str, int]) -> list[dict]`
  (lève `CartLineError` sur la première ligne invalide — le checkout attrape
  et affiche un message par ligne, jamais un rejet opaque) ;
  `create_order(shop_id: str, *, customer_name: str, customer_phone: str, customer_address: str, lines: list[dict]) -> str`
  (retourne l'`orderId` créé). Consommés par la Task 4.

- [ ] **Step 1: Écrire les tests**

Créer `storefront/tests_orders.py` :

```python
from unittest.mock import MagicMock, patch

from django.test import TestCase

from storefront.orders import CartLineError, build_order_lines, create_order


class BuildOrderLinesTests(TestCase):
    @patch('storefront.orders.fb_read.get_public_products_by_ids')
    def test_construit_les_lignes_avec_prix_et_nom_reels(self, mock_get):
        mock_get.return_value = {
            'p1': {'id': 'p1', 'name': 'Sac', 'price': 1000, 'inStock': True},
        }
        lines = build_order_lines('s1', {'p1': 2})
        self.assertEqual(lines, [{'productId': 'p1', 'name': 'Sac', 'price': 1000, 'qty': 2}])

    @patch('storefront.orders.fb_read.get_public_products_by_ids')
    def test_leve_cart_line_error_si_produit_absent(self, mock_get):
        mock_get.return_value = {}
        with self.assertRaises(CartLineError) as ctx:
            build_order_lines('s1', {'p1': 1})
        self.assertEqual(ctx.exception.product_id, 'p1')
        self.assertEqual(ctx.exception.reason, 'unavailable')

    @patch('storefront.orders.fb_read.get_public_products_by_ids')
    def test_leve_cart_line_error_si_stock_insuffisant(self, mock_get):
        mock_get.return_value = {
            'p1': {'id': 'p1', 'name': 'Sac', 'price': 1000, 'inStock': True, 'stockQty': 1},
        }
        with self.assertRaises(CartLineError) as ctx:
            build_order_lines('s1', {'p1': 5})
        self.assertEqual(ctx.exception.reason, 'insufficient_stock')
        self.assertEqual(ctx.exception.available, 1)

    @patch('storefront.orders.fb_read.get_public_products_by_ids')
    def test_leve_cart_line_error_si_hors_stock(self, mock_get):
        mock_get.return_value = {
            'p1': {'id': 'p1', 'name': 'Sac', 'price': 1000, 'inStock': False, 'stockQty': 0},
        }
        with self.assertRaises(CartLineError) as ctx:
            build_order_lines('s1', {'p1': 1})
        self.assertEqual(ctx.exception.reason, 'insufficient_stock')
        self.assertEqual(ctx.exception.available, 0)


class CreateOrderTests(TestCase):
    @patch('storefront.orders.fb.db')
    def test_ecrit_le_document_storeOrders_avec_les_bons_champs(self, mock_db):
        mock_add = mock_db.return_value.collection.return_value.add
        mock_doc_ref = MagicMock()
        mock_doc_ref.id = 'order123'
        mock_add.return_value = (None, mock_doc_ref)

        order_id = create_order(
            's1',
            customer_name='Awa',
            customer_phone='2290100000000',
            customer_address='Cotonou',
            lines=[{'productId': 'p1', 'name': 'Sac', 'price': 1000, 'qty': 2}],
        )

        self.assertEqual(order_id, 'order123')
        written = mock_add.call_args[0][0]
        self.assertEqual(written['shopId'], 's1')
        self.assertEqual(written['status'], 'pending')
        self.assertEqual(written['paymentMode'], 'cash_on_delivery')
        self.assertIsNone(written['paymentRef'])
        self.assertEqual(written['totalAmount'], 2000)
        self.assertEqual(written['customerName'], 'Awa')
        self.assertEqual(written['items'][0]['productId'], 'p1')
```

`stockQty` : ajouter ce champ interne (quantité exacte, jamais exposée au
template public) au dict renvoyé par `_serialize_product`
(`storefront/firebase_read.py`) — nécessaire pour que `build_order_lines`
puisse valider la quantité demandée. Modifier `_serialize_product` (juste
avant `'inStock': ...`) :

```python
        'stockQty': data.get('quantity') or 0,
        'inStock': (data.get('quantity') or 0) > 0,
```

Ce champ ne doit **jamais** être passé aux templates publics
(`home.html`/`product_detail.html`) — seul `inStock` (booléen) l'est déjà ;
vérifier qu'aucun template n'affiche `product.stockQty` avant de continuer
(recherche `grep -rn stockQty templates/` doit ne rien renvoyer côté
templates).

- [ ] **Step 2: Lancer les tests pour vérifier qu'ils échouent**

Run: `python manage.py test storefront.tests_orders`
Expected: FAIL (import error, `storefront.orders` n'existe pas).

- [ ] **Step 3: Implémenter `storefront/orders.py`**

```python
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
```

- [ ] **Step 4: Lancer les tests pour vérifier qu'ils passent**

Run: `python manage.py test storefront.tests_orders storefront.tests_firebase_read`
Expected: PASS (aucune régression sur `firebase_read`).

- [ ] **Step 5: Commit**

```bash
git add storefront/orders.py storefront/tests_orders.py storefront/firebase_read.py
git commit -m "feat(storefront): validation stock réel + création storeOrders (cash_on_delivery)"
```

---

### Task 4: `storefront/ratelimit.py` — throttle simple par session

**Files:**
- Create: `storefront/ratelimit.py`
- Test: `storefront/tests_ratelimit.py`

**Interfaces:**
- Produces: `too_many_attempts(request, key: str, *, max_attempts: int = 5, window_seconds: int = 600) -> bool`
  (enregistre une tentative ET renvoie `True` si la limite est dépassée —
  un seul appel par tentative de checkout). Consommé par la Task 5.

- [ ] **Step 1: Écrire les tests**

Créer `storefront/tests_ratelimit.py` :

```python
import time
from unittest.mock import patch

from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory, TestCase

from storefront.ratelimit import too_many_attempts


def _request_with_session():
    request = RequestFactory().get('/')
    SessionMiddleware(lambda r: None).process_request(request)
    request.session.save()
    return request


class RateLimitTests(TestCase):
    def setUp(self):
        self.request = _request_with_session()

    def test_sous_la_limite_renvoie_faux(self):
        for _ in range(4):
            self.assertFalse(too_many_attempts(self.request, 'checkout', max_attempts=5))

    def test_atteint_la_limite_renvoie_vrai(self):
        for _ in range(5):
            too_many_attempts(self.request, 'checkout', max_attempts=5)
        self.assertTrue(too_many_attempts(self.request, 'checkout', max_attempts=5))

    def test_cles_differentes_sont_independantes(self):
        for _ in range(5):
            too_many_attempts(self.request, 'checkout', max_attempts=5)
        self.assertFalse(too_many_attempts(self.request, 'autre_action', max_attempts=5))

    def test_fenetre_expiree_reinitialise_le_compteur(self):
        now = [1_000_000.0]
        with patch('storefront.ratelimit.time.time', side_effect=lambda: now[0]):
            for _ in range(5):
                too_many_attempts(self.request, 'checkout', max_attempts=5, window_seconds=600)
            self.assertTrue(too_many_attempts(self.request, 'checkout', max_attempts=5, window_seconds=600))
            now[0] += 601
            self.assertFalse(too_many_attempts(self.request, 'checkout', max_attempts=5, window_seconds=600))
```

- [ ] **Step 2: Lancer les tests pour vérifier qu'ils échouent**

Run: `python manage.py test storefront.tests_ratelimit`
Expected: FAIL (import error, `storefront.ratelimit` n'existe pas).

- [ ] **Step 3: Implémenter `storefront/ratelimit.py`**

```python
"""Throttle anti-spam minimal, par session Django — pas de compte client
donc pas d'autre identifiant fiable côté serveur ; suffisant pour dissuader
un spam basique de faux `storeOrders` sans dépendance externe (cf. spec,
section Sécurité)."""
import time

_SESSION_PREFIX = 'ratelimit_'


def too_many_attempts(request, key: str, *, max_attempts: int = 5,
                       window_seconds: int = 600) -> bool:
    """Enregistre une tentative pour `key` et renvoie True si `max_attempts`
    a été atteint/dépassé dans la fenêtre `window_seconds`. Les tentatives
    hors fenêtre sont purgées à chaque appel (la session ne grossit jamais
    indéfiniment)."""
    session_key = f'{_SESSION_PREFIX}{key}'
    now = time.time()
    attempts = [t for t in request.session.get(session_key, []) if now - t < window_seconds]
    attempts.append(now)
    request.session[session_key] = attempts
    request.session.modified = True
    return len(attempts) > max_attempts
```

- [ ] **Step 4: Lancer les tests pour vérifier qu'ils passent**

Run: `python manage.py test storefront.tests_ratelimit`
Expected: PASS (4/4).

- [ ] **Step 5: Commit**

```bash
git add storefront/ratelimit.py storefront/tests_ratelimit.py
git commit -m "feat(storefront): throttle par session sur la création de commande"
```

---

### Task 5: `storefront/notify.py` — notification push nouvelle commande

**Files:**
- Create: `storefront/notify.py`
- Test: `storefront/tests_notify.py`

**Interfaces:**
- Consumes: `get_shop_owner_uid` (Task 2),
  `billing.firebase_service.tokens_for_uid/send_push/record_notification`
  (existants).
- Produces: `notify_new_order(shop_id: str, shop_name: str, order_id: str, total_amount: float) -> None`.
  Consommé par la Task 6.

- [ ] **Step 1: Écrire les tests**

Créer `storefront/tests_notify.py` :

```python
from unittest.mock import MagicMock, patch

from django.test import TestCase

from storefront.notify import notify_new_order


class NotifyNewOrderTests(TestCase):
    @patch('storefront.notify.fb_service.record_notification')
    @patch('storefront.notify.fb_service.send_push')
    @patch('storefront.notify.fb_service.tokens_for_uid')
    @patch('storefront.notify.fb_read.get_shop_owner_uid')
    def test_envoie_le_push_et_enregistre_l_historique(
        self, mock_owner, mock_tokens, mock_send, mock_record,
    ):
        mock_owner.return_value = 'owner1'
        mock_tokens.return_value = ['tok1', 'tok2']

        notify_new_order('s1', 'Ma Boutique', 'order123', 5000)

        mock_tokens.assert_called_once_with('owner1')
        mock_send.assert_called_once()
        args, kwargs = mock_send.call_args
        self.assertEqual(args[0], ['tok1', 'tok2'])
        self.assertIn('Ma Boutique', args[1])
        mock_record.assert_called_once()
        record_kwargs = mock_record.call_args.kwargs
        self.assertEqual(record_kwargs['ntype'], 'new_online_order')

    @patch('storefront.notify.fb_service.record_notification')
    @patch('storefront.notify.fb_service.send_push')
    @patch('storefront.notify.fb_service.tokens_for_uid')
    @patch('storefront.notify.fb_read.get_shop_owner_uid')
    def test_ne_leve_pas_si_boutique_sans_proprietaire_resolu(
        self, mock_owner, mock_tokens, mock_send, mock_record,
    ):
        mock_owner.return_value = None

        notify_new_order('s1', 'Ma Boutique', 'order123', 5000)

        mock_tokens.assert_not_called()
        mock_send.assert_not_called()
        mock_record.assert_not_called()
```

- [ ] **Step 2: Lancer les tests pour vérifier qu'ils échouent**

Run: `python manage.py test storefront.tests_notify`
Expected: FAIL (import error, `storefront.notify` n'existe pas).

- [ ] **Step 3: Implémenter `storefront/notify.py`**

```python
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
    title = 'Nouvelle commande en ligne'
    body = f'{shop_name} : nouvelle commande de {total_amount:.0f}'
    data = {'type': 'new_online_order', 'orderId': order_id, 'shopId': shop_id}
    fb_service.send_push(tokens, title, body, data)
    fb_service.record_notification(
        owner_uid, title=title, body=body, data=data, ntype='new_online_order')
```

- [ ] **Step 4: Lancer les tests pour vérifier qu'ils passent**

Run: `python manage.py test storefront.tests_notify`
Expected: PASS (2/2).

- [ ] **Step 5: Commit**

```bash
git add storefront/notify.py storefront/tests_notify.py
git commit -m "feat(storefront): notification push au propriétaire à la création d'une commande"
```

---

### Task 6: Vues panier/checkout + templates + urls + i18n

**Files:**
- Modify: `storefront/views.py`
- Modify: `storefront/urls.py`
- Modify: `storefront/i18n.py`
- Modify: `templates/storefront/base.html`
- Modify: `templates/storefront/product_detail.html`
- Create: `templates/storefront/cart.html`
- Create: `templates/storefront/checkout.html`
- Create: `templates/storefront/order_confirmation.html`
- Test: `storefront/tests_views_cart.py`

**Interfaces:**
- Consumes: `cart.*` (Task 1), `orders.build_order_lines/create_order/CartLineError`
  (Task 3), `ratelimit.too_many_attempts` (Task 4), `notify.notify_new_order`
  (Task 5), `firebase_read.get_public_products_by_ids` (Task 2).
- Produces: rien de consommé par d'autres tâches — dernière tâche du plan.

**Priorité expérience utilisateur** : chaque action panier (ajouter, changer
quantité, retirer) redirige vers la page d'où elle vient
(`HTTP_REFERER`/paramètre `next`, repli sur l'accueil) avec un message flash
(`django.contrib.messages`, déjà activé) — jamais une page blanche de
confirmation qui casse la navigation. Le badge du panier (nombre d'articles)
est visible sur toutes les pages via le header commun. Au checkout, une
erreur de stock affiche le nom du produit concerné et la quantité
disponible, pas un message générique.

- [ ] **Step 1: Ajouter les clés i18n**

Dans `storefront/i18n.py`, ajouter à `STRINGS` (avant la fermeture `}`) :

```python
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
```

- [ ] **Step 2: Vérifier qu'il n'y a pas de collision de clé**

Run: `python -c "
import ast
tree = ast.parse(open('storefront/i18n.py').read())
d = next(n for n in ast.walk(tree) if isinstance(n, ast.Dict))
keys = [k.value for k in d.keys]
dupes = {k for k in keys if keys.count(k) > 1}
print('OK, aucun doublon' if not dupes else dupes)
"`
Expected: `OK, aucun doublon`

- [ ] **Step 3: Ajouter les vues dans `storefront/views.py`**

Ajouter les imports en tête de fichier, après `from .i18n import STRINGS, t` :

```python
from django.contrib import messages
from django.shortcuts import redirect
from django.views.decorators.http import require_POST

from . import cart as cart_mod
from . import notify
from . import ratelimit
from .orders import CartLineError, build_order_lines, create_order
```

Ajouter, après la fonction `product_detail` (avant `sitemap`) :

```python


def _redirect_back(request):
    """Retour à la page d'origine (repli accueil) — préserve la navigation
    du visiteur après une action panier, jamais une page blanche."""
    return redirect(request.META.get('HTTP_REFERER') or 'storefront_home')


@require_POST
def add_to_cart_view(request):
    shop = _load_shop_or_none(request)
    if shop is None:
        raise Http404('Boutique introuvable')
    lang = _lang(request)
    product_id = request.POST.get('product_id', '')
    try:
        qty = max(1, int(request.POST.get('qty', 1)))
    except ValueError:
        qty = 1
    cart_mod.add_to_cart(request, product_id, qty)
    messages.success(request, t('added_to_cart', lang))
    return _redirect_back(request)


@require_POST
def update_cart_view(request):
    shop = _load_shop_or_none(request)
    if shop is None:
        raise Http404('Boutique introuvable')
    product_id = request.POST.get('product_id', '')
    try:
        qty = int(request.POST.get('qty', 0))
    except ValueError:
        qty = 0
    cart_mod.set_quantity(request, product_id, qty)
    return redirect('storefront_cart')


@require_POST
def remove_from_cart_view(request):
    shop = _load_shop_or_none(request)
    if shop is None:
        raise Http404('Boutique introuvable')
    cart_mod.remove_from_cart(request, request.POST.get('product_id', ''))
    return redirect('storefront_cart')


def cart_view(request):
    lang = _lang(request)
    shop = _load_shop_or_none(request)
    if shop is None:
        raise Http404('Boutique introuvable')
    cart = cart_mod.get_cart(request)
    products = fb_read.get_public_products_by_ids(shop['id'], list(cart.keys()))
    lines = []
    for product_id, qty in cart.items():
        product = products.get(product_id)
        if product is None:
            continue  # produit devenu indisponible : simplement absent de l'affichage
        lines.append({'product': product, 'qty': qty, 'subtotal': product['price'] * qty})
    total = sum(line['subtotal'] for line in lines)
    return render(request, 'storefront/cart.html', {
        'shop': shop, 'lang': lang, 't': _strings(lang),
        'lines': lines, 'total': total,
    })


def checkout_view(request):
    lang = _lang(request)
    shop = _load_shop_or_none(request)
    if shop is None:
        raise Http404('Boutique introuvable')
    if not shop.get('allowCartOrder'):
        return _unavailable(request, lang, shop=shop)

    cart = cart_mod.get_cart(request)
    if not cart:
        return redirect('storefront_cart')

    if request.method == 'POST':
        if ratelimit.too_many_attempts(request, 'checkout'):
            messages.error(request, t('too_many_attempts', lang))
            return redirect('storefront_checkout')

        try:
            lines = build_order_lines(shop['id'], cart)
        except CartLineError as err:
            if err.reason == 'unavailable':
                cart_mod.remove_from_cart(request, err.product_id)
                messages.error(request, t('stock_error_unavailable', lang).format(name=err.product_name))
            else:
                cart_mod.set_quantity(request, err.product_id, err.available or 0)
                messages.error(
                    request,
                    t('stock_error_insufficient', lang).format(
                        name=err.product_name, available=err.available),
                )
            return redirect('storefront_cart')

        order_id = create_order(
            shop['id'],
            customer_name=request.POST.get('customer_name', '').strip(),
            customer_phone=request.POST.get('customer_phone', '').strip(),
            customer_address=request.POST.get('customer_address', '').strip(),
            lines=lines,
        )
        total = sum(line['price'] * line['qty'] for line in lines)
        notify.notify_new_order(shop['id'], shop['name'], order_id, total)
        cart_mod.clear_cart(request)
        return render(request, 'storefront/order_confirmation.html', {
            'shop': shop, 'lang': lang, 't': _strings(lang), 'order_id': order_id,
        })

    products = fb_read.get_public_products_by_ids(shop['id'], list(cart.keys()))
    lines = [
        {'product': products[pid], 'qty': qty, 'subtotal': products[pid]['price'] * qty}
        for pid, qty in cart.items() if pid in products
    ]
    total = sum(line['subtotal'] for line in lines)
    return render(request, 'storefront/checkout.html', {
        'shop': shop, 'lang': lang, 't': _strings(lang), 'lines': lines, 'total': total,
    })
```

Note : `shop['allowCartOrder']` n'existe pas encore dans le dict renvoyé par
`get_shop_by_slug` (`storefront/firebase_read.py`) — ajouter cette clé.
Modifier `get_shop_by_slug`, juste après la ligne
`'allowContact': bool(settings_.get('allowContact', True)),` :

```python
        'allowCartOrder': bool(settings_.get('allowCartOrder', False)),
```

- [ ] **Step 4: Ajouter les routes dans `storefront/urls.py`**

Remplacer le contenu par :

```python
from django.urls import path

from . import views

urlpatterns = [
    path('', views.home, name='storefront_home'),
    path('produit/<str:product_slug>', views.product_detail, name='storefront_product'),
    path('panier', views.cart_view, name='storefront_cart'),
    path('panier/ajouter', views.add_to_cart_view, name='storefront_cart_add'),
    path('panier/modifier', views.update_cart_view, name='storefront_cart_update'),
    path('panier/retirer', views.remove_from_cart_view, name='storefront_cart_remove'),
    path('commande', views.checkout_view, name='storefront_checkout'),
    path('sitemap.xml', views.sitemap, name='storefront_sitemap'),
    path('robots.txt', views.robots, name='storefront_robots'),
]
```

- [ ] **Step 5: Ajouter le lien panier + badge dans `templates/storefront/base.html`**

Remplacer le bloc `<nav class="flex items-center gap-4 ...">` (header du
haut) :

```html
            <nav class="flex items-center gap-4 text-sm font-semibold">
                <a href="{% url 'storefront_home' %}" class="text-shopPrimary">{{ t.home|default:"" }}</a>
                {% if shop.allowCartOrder %}
                <a href="{% url 'storefront_cart' %}" class="relative">
                    <span>&#128722;</span>
                    {% if cart_count %}
                    <span class="absolute -top-2 -right-2 bg-shopPrimary text-white text-[10px] rounded-full w-4 h-4 flex items-center justify-center">{{ cart_count }}</span>
                    {% endif %}
                </a>
                {% endif %}
            </nav>
```

Puis, dans la barre de navigation basse, remplacer le bloc `{% if
shop.allowContact %}...{% endif %}` par (ajout du panier avant Contact,
conforme à la spec point 10 : Panier visible seulement si le mode est actif) :

```html
        {% if shop.allowCartOrder %}
        <a href="{% url 'storefront_cart' %}" class="flex flex-col items-center gap-1">
            <span>&#128722;</span><span>{{ t.cart|default:"" }}{% if cart_count %} ({{ cart_count }}){% endif %}</span>
        </a>
        {% endif %}
        {% if shop.allowContact %}
        <a href="https://wa.me/{{ shop.whatsappNumber }}" class="flex flex-col items-center gap-1">
            <span>&#9742;</span><span>{{ t.contact|default:"" }}</span>
        </a>
        {% endif %}
```

Pour que `cart_count` soit disponible sur TOUTES les pages sans le passer
manuellement dans chaque vue, ajouter un context processor. Créer
`storefront/context_processors.py` :

```python
"""Context processor exposant le nombre d'articles du panier à tous les
templates du site public (badge header/nav basse), sans devoir le repasser
dans le contexte de chaque vue."""
from . import cart as cart_mod


def cart_context(request):
    if not hasattr(request, 'session'):
        return {'cart_count': 0}
    return {'cart_count': cart_mod.cart_item_count(request)}
```

Puis l'enregistrer dans `core/settings.py`, dans `TEMPLATES[0]['OPTIONS']['context_processors']`
(chercher ce bloc — ajouter `'storefront.context_processors.cart_context',`
à la liste existante, sans retirer les entrées déjà présentes).

- [ ] **Step 6: Ajouter le bouton "Ajouter au panier" dans `templates/storefront/product_detail.html`**

Ouvrir le fichier, repérer le bloc du bouton "Contacter sur WhatsApp"
(`{% if shop.allowContact %}`) et ajouter juste avant :

```html
{% if shop.allowCartOrder and product.inStock %}
<form method="post" action="{% url 'storefront_cart_add' %}" class="mb-3">
    {% csrf_token %}
    <input type="hidden" name="product_id" value="{{ product.id }}">
    <input type="hidden" name="qty" value="1">
    <button type="submit" class="w-full bg-shopPrimary text-white font-semibold rounded-xl py-3">
        {{ t.add_to_cart }}
    </button>
</form>
{% endif %}
```

(Intégration exacte dépendante du layout actuel du fichier — ajouter ce
bloc au même niveau que le bouton WhatsApp existant, sans le remplacer.)

- [ ] **Step 7: Créer `templates/storefront/cart.html`**

```html
{% extends "storefront/base.html" %}
{% block content %}
<div class="max-w-3xl mx-auto px-4 py-6">
    <h1 class="text-xl font-bold mb-4">{{ t.cart }}</h1>

    {% if messages %}
    <div class="mb-4 space-y-2">
        {% for message in messages %}
        <div class="rounded-lg px-4 py-2 text-sm {% if message.tags == 'error' %}bg-red-50 text-red-700{% else %}bg-green-50 text-green-700{% endif %}">
            {{ message }}
        </div>
        {% endfor %}
    </div>
    {% endif %}

    {% if not lines %}
    <p class="text-gray-500">{{ t.cart_empty }}</p>
    {% else %}
    <div class="space-y-4">
        {% for line in lines %}
        <div class="flex items-center justify-between border-b border-gray-100 pb-4">
            <div>
                <p class="font-semibold">{{ line.product.name }}</p>
                <p class="text-sm text-gray-500">{{ line.product.price }} x {{ line.qty }}</p>
            </div>
            <div class="flex items-center gap-3">
                <form method="post" action="{% url 'storefront_cart_update' %}" class="flex items-center gap-2">
                    {% csrf_token %}
                    <input type="hidden" name="product_id" value="{{ line.product.id }}">
                    <input type="number" name="qty" value="{{ line.qty }}" min="1" class="w-16 border border-gray-200 rounded-lg px-2 py-1 text-sm">
                    <button type="submit" class="text-xs font-semibold text-shopPrimary">{{ t.quantity }}</button>
                </form>
                <form method="post" action="{% url 'storefront_cart_remove' %}">
                    {% csrf_token %}
                    <input type="hidden" name="product_id" value="{{ line.product.id }}">
                    <button type="submit" class="text-xs font-semibold text-red-600">{{ t.remove }}</button>
                </form>
            </div>
        </div>
        {% endfor %}
    </div>
    <div class="flex items-center justify-between mt-6 font-bold text-lg">
        <span>{{ t.total }}</span>
        <span>{{ total }}</span>
    </div>
    <a href="{% url 'storefront_checkout' %}" class="mt-4 block text-center bg-shopPrimary text-white font-semibold rounded-xl py-3">
        {{ t.checkout }}
    </a>
    {% endif %}
</div>
{% endblock %}
```

- [ ] **Step 8: Créer `templates/storefront/checkout.html`**

```html
{% extends "storefront/base.html" %}
{% block content %}
<div class="max-w-md mx-auto px-4 py-6">
    <h1 class="text-xl font-bold mb-4">{{ t.checkout }}</h1>

    {% if messages %}
    <div class="mb-4 space-y-2">
        {% for message in messages %}
        <div class="rounded-lg px-4 py-2 text-sm bg-red-50 text-red-700">{{ message }}</div>
        {% endfor %}
    </div>
    {% endif %}

    <div class="mb-6 space-y-2">
        {% for line in lines %}
        <div class="flex justify-between text-sm">
            <span>{{ line.product.name }} x {{ line.qty }}</span>
            <span>{{ line.subtotal }}</span>
        </div>
        {% endfor %}
        <div class="flex justify-between font-bold border-t border-gray-100 pt-2">
            <span>{{ t.total }}</span>
            <span>{{ total }}</span>
        </div>
    </div>

    <form method="post" class="space-y-3">
        {% csrf_token %}
        <input type="text" name="customer_name" required placeholder="{{ t.customer_name }}" class="w-full border border-gray-200 rounded-lg px-3 py-2">
        <input type="tel" name="customer_phone" required placeholder="{{ t.customer_phone }}" class="w-full border border-gray-200 rounded-lg px-3 py-2">
        <input type="text" name="customer_address" required placeholder="{{ t.customer_address }}" class="w-full border border-gray-200 rounded-lg px-3 py-2">
        <p class="text-sm text-gray-500">{{ t.payment_cash_on_delivery }}</p>
        <button type="submit" class="w-full bg-shopPrimary text-white font-semibold rounded-xl py-3">
            {{ t.confirm_order }}
        </button>
    </form>
</div>
{% endblock %}
```

- [ ] **Step 9: Créer `templates/storefront/order_confirmation.html`**

```html
{% extends "storefront/base.html" %}
{% block content %}
<div class="max-w-md mx-auto px-4 py-10 text-center">
    <p class="text-4xl mb-4">&#10003;</p>
    <h1 class="text-xl font-bold mb-2">{{ t.order_confirmed_title }}</h1>
    <p class="text-gray-500 mb-6">{{ t.order_confirmed_body }}</p>
    <a href="{% url 'storefront_home' %}" class="inline-block bg-shopPrimary text-white font-semibold rounded-xl px-6 py-3">
        {{ t.back_to_home }}
    </a>
</div>
{% endblock %}
```

- [ ] **Step 10: Écrire les tests des vues**

Créer `storefront/tests_views_cart.py` :

```python
from unittest.mock import MagicMock, patch

from django.test import Client, TestCase, override_settings

_SHOP = {
    'id': 's1', 'name': 'Ma Boutique', 'publicSlug': 'ma-boutique',
    'storefrontEnabled': True, 'currency': 'XOF', 'heroImageUrl': None,
    'heroTitle_fr': None, 'heroTitle_en': None, 'heroSubtitle_fr': None,
    'heroSubtitle_en': None, 'aboutText_fr': None, 'aboutText_en': None,
    'seoDescription_fr': None, 'seoDescription_en': None,
    'whatsappNumber': '2290100000000', 'allowContact': True,
    'allowCartOrder': True, 'primaryColorHex': '#1565C0', 'isPro': True,
}
_PRODUCT = {
    'id': 'p1', 'name': 'Sac', 'slug': 'sac', 'url_slug': 'p1-sac',
    'description': '', 'price': 1000, 'discountPrice': None,
    'discountPercent': None, 'images': [], 'videoUrl': None,
    'categoryId': 'c1', 'stockQty': 5, 'inStock': True, 'createdAt': None,
}


@override_settings(STOREFRONT_BASE_DOMAINS=['compa.nouyon.site'], ALLOWED_HOSTS=['*'])
class CartCheckoutFlowTests(TestCase):
    def setUp(self):
        self.client = Client(HTTP_HOST='ma-boutique.compa.nouyon.site')

    @patch('storefront.firebase_read.fb.db')
    @patch('storefront.views.fb_read.get_shop_by_slug')
    def test_ajouter_puis_voir_le_panier(self, mock_shop, mock_db):
        mock_shop.return_value = _SHOP
        doc = MagicMock()
        doc.exists = True
        doc.id = 'p1'
        doc.to_dict.return_value = {'shopId': 's1', 'name': 'Sac', 'price': 1000, 'quantity': 5}
        mock_db.return_value.collection.return_value.document.return_value.get.return_value = doc

        self.client.post('/panier/ajouter', {'product_id': 'p1', 'qty': 2})
        response = self.client.get('/panier')

        self.assertContains(response, 'Sac')
        self.assertContains(response, '2000')  # 1000 x 2

    @patch('storefront.notify.notify_new_order')
    @patch('storefront.orders.fb.db')
    @patch('storefront.firebase_read.fb.db')
    @patch('storefront.views.fb_read.get_shop_by_slug')
    def test_checkout_cree_la_commande_et_vide_le_panier(
        self, mock_shop, mock_read_db, mock_orders_db, mock_notify,
    ):
        mock_shop.return_value = _SHOP
        doc = MagicMock()
        doc.exists = True
        doc.id = 'p1'
        doc.to_dict.return_value = {'shopId': 's1', 'name': 'Sac', 'price': 1000, 'quantity': 5}
        mock_read_db.return_value.collection.return_value.document.return_value.get.return_value = doc

        mock_doc_ref = MagicMock()
        mock_doc_ref.id = 'order123'
        mock_orders_db.return_value.collection.return_value.add.return_value = (None, mock_doc_ref)

        self.client.post('/panier/ajouter', {'product_id': 'p1', 'qty': 2})
        response = self.client.post('/commande', {
            'customer_name': 'Awa', 'customer_phone': '229010000',
            'customer_address': 'Cotonou',
        })

        self.assertContains(response, 'Commande envoyée')
        mock_notify.assert_called_once()
        self.assertEqual(self.client.session.get('cart', {}), {})

    @patch('storefront.views.fb_read.get_shop_by_slug')
    def test_checkout_redirige_vers_panier_si_vide(self, mock_shop):
        mock_shop.return_value = _SHOP
        response = self.client.get('/commande')
        self.assertRedirects(response, '/panier')

    @patch('storefront.views.fb_read.get_shop_by_slug')
    def test_checkout_indisponible_si_allowCartOrder_faux(self, mock_shop):
        mock_shop.return_value = {**_SHOP, 'allowCartOrder': False}
        with self.settings():
            response = self.client.get('/commande')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "n'est plus disponible", status_code=200)
```

- [ ] **Step 11: Lancer les tests pour vérifier qu'ils passent**

Run: `python manage.py test storefront`
Expected: PASS (toutes les classes du module `storefront`, y compris les
Tasks 1-5 et les tests préexistants — aucune régression).

- [ ] **Step 12: Vérifier**

Run: `python manage.py check`
Expected: `System check identified no issues (0 silenced).`

- [ ] **Step 13: Direction artistique — comparaison avec la maquette**

Ouvrir `/home/jey/Téléchargements/modelsite.jpg` et comparer visuellement
les pages `cart.html`/`checkout.html`/`order_confirmation.html` (structure,
densité, proportions) — seule la couleur change (bleu au lieu de violet),
cf. spec section "Direction artistique". Ajuster si un écart de structure
est visible (pas seulement la palette).

- [ ] **Step 14: Commit**

```bash
git add storefront/views.py storefront/urls.py storefront/i18n.py \
        storefront/firebase_read.py storefront/context_processors.py \
        storefront/tests_views_cart.py core/settings.py \
        templates/storefront/base.html templates/storefront/product_detail.html \
        templates/storefront/cart.html templates/storefront/checkout.html \
        templates/storefront/order_confirmation.html
git commit -m "feat(storefront): panier, checkout et confirmation de commande (site public)"
```

---

## Notes hors-scope pour la suite

- Paiement en ligne (FedaPay) — Phase 3, dépend de ce plan (panier/checkout)
  déjà en place.
- Compteurs `ordersCreated`/`ordersPaid` de `storefrontStats` — dépend du
  chantier statistiques Phase 1 non fait séparément.
- Écran "Commandes en ligne" + `SaleModel.sourceOrderId` côté app Flutter —
  plan complémentaire dans `smart_stock`
  (`docs/superpowers/plans/2026-07-24-boutique-en-ligne-phase2-flutter.md`).
