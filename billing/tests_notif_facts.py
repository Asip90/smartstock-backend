"""Tests pour les constructeurs de faits du moteur de notifications IA.

Utilise un faux client Firestore (FakeDB/FakeQuery/FakeDoc) pour ne jamais
toucher au vrai Firestore.
"""
from datetime import datetime, time, timedelta

from django.test import SimpleTestCase
from django.utils import timezone

from billing.notif_facts import (
    evening_facts,
    first_name,
    morning_facts,
    stock_facts,
)


class FakeDoc:
    """Document Firestore minimal : `.id` + `.to_dict()` (+ `.exists`)."""

    def __init__(self, doc_id, data=None, exists=True):
        self.id = doc_id
        self._data = data or {}
        self.exists = exists

    def to_dict(self):
        return dict(self._data)


class FakeQuery:
    """Requête chaînable : `.where(...).where(...).stream()`.

    Applique les filtres `==`, `>=`, `<` sur les champs des documents fournis.
    """

    def __init__(self, docs):
        self._docs = list(docs)

    def where(self, field, op, value):
        def keep(doc):
            v = doc.to_dict().get(field)
            if op == '==':
                return v == value
            if op == '>=':
                return v is not None and v >= value
            if op == '<':
                return v is not None and v < value
            raise ValueError(f'Opérateur non supporté : {op}')

        return FakeQuery([d for d in self._docs if keep(d)])

    def stream(self):
        return iter(self._docs)


class FakeCollectionDocs:
    """Permet `.document(id)` sur une collection (pour `users`)."""

    def __init__(self, docs_by_id):
        self._docs_by_id = docs_by_id

    def document(self, doc_id):
        return _FakeDocRef(self._docs_by_id.get(doc_id))


class _FakeDocRef:
    def __init__(self, doc):
        self._doc = doc

    def get(self):
        if self._doc is not None:
            return self._doc
        return FakeDoc('missing', {}, exists=False)


class FakeDB:
    """Faux client Firestore : `.collection(name)` -> objet avec `.where`,
    `.stream`, `.document` selon la collection demandée."""

    def __init__(self, collections=None, users=None, raise_on=None):
        self._collections = collections or {}
        self._users = users or {}
        self._raise_on = raise_on or set()

    def collection(self, name):
        if name in self._raise_on:
            raise RuntimeError(f'collection {name} indisponible')
        if name == 'users':
            return FakeCollectionDocs(self._users)
        docs = self._collections.get(name, [])
        query = FakeQuery(docs)
        # Permet aussi `.document(...)` sur d'autres collections si besoin.
        query.document = lambda doc_id: _FakeDocRef(None)
        return query


def _today_ts():
    now = timezone.localtime()
    start_of_today = timezone.make_aware(datetime.combine(now.date(), time.min))
    return start_of_today + timedelta(hours=10)


def _yesterday_ts():
    now = timezone.localtime()
    start_of_today = timezone.make_aware(datetime.combine(now.date(), time.min))
    return start_of_today - timedelta(hours=2)


class EveningFactsTests(SimpleTestCase):
    def test_aggregates_count_revenue_cash_credit(self):
        today_ts = _today_ts()
        yesterday_ts = _yesterday_ts()

        sales = [
            FakeDoc('s1', {
                'shopId': 'shop1', 'totalAmount': 1000, 'amountPaid': 1000,
                'saleDate': today_ts,
            }),
            FakeDoc('s2', {
                'shopId': 'shop1', 'totalAmount': 500, 'amountPaid': 200,
                'saleDate': today_ts,
            }),
            # Vente d'hier : ne doit pas compter.
            FakeDoc('s3', {
                'shopId': 'shop1', 'totalAmount': 9999, 'amountPaid': 9999,
                'saleDate': yesterday_ts,
            }),
            # Autre boutique : ne doit pas compter.
            FakeDoc('s4', {
                'shopId': 'shop2', 'totalAmount': 100, 'amountPaid': 100,
                'saleDate': today_ts,
            }),
        ]
        db = FakeDB(collections={'sales': sales})

        facts = evening_facts(db, 'shop1', {'name': 'Ma Boutique'})

        self.assertEqual(facts['shop_name'], 'Ma Boutique')
        self.assertEqual(facts['count'], 2)
        self.assertEqual(facts['revenue'], 1500.0)
        self.assertEqual(facts['cash'], 1200.0)
        self.assertEqual(facts['credit'], 300.0)


class StockFactsTests(SimpleTestCase):
    def test_returns_count_and_samples_sorted_by_qty(self):
        produits = [
            FakeDoc('p1', {'shopId': 'shop1', 'name': 'Riz', 'quantity': 3, 'nbreCritique': 5}),
            FakeDoc('p2', {'shopId': 'shop1', 'name': 'Sucre', 'quantity': 1, 'nbreCritique': 5}),
            FakeDoc('p3', {'shopId': 'shop1', 'name': 'Huile', 'quantity': 2, 'nbreCritique': 5}),
            FakeDoc('p4', {'shopId': 'shop1', 'name': 'Sel', 'quantity': 0, 'nbreCritique': 5}),
            # Au-dessus du seuil : exclu.
            FakeDoc('p5', {'shopId': 'shop1', 'name': 'Lait', 'quantity': 10, 'nbreCritique': 5}),
            # Seuil par défaut (pas de nbreCritique), quantity > 5 -> exclu.
            FakeDoc('p6', {'shopId': 'shop1', 'name': 'Pates', 'quantity': 8}),
            # Autre boutique -> exclu.
            FakeDoc('p7', {'shopId': 'shop2', 'name': 'Cafe', 'quantity': 0, 'nbreCritique': 5}),
        ]
        db = FakeDB(collections={'produits': produits})

        facts = stock_facts(db, 'shop1', {'name': 'Ma Boutique'})

        self.assertEqual(facts['shop_name'], 'Ma Boutique')
        self.assertEqual(facts['count'], 4)
        # Trié par quantité croissante, limité à 3.
        self.assertEqual(facts['samples'], ['Sel', 'Sucre', 'Huile'])


class MorningFactsTests(SimpleTestCase):
    def test_yesterday_aggregation_and_ruptures(self):
        today_ts = _today_ts()
        yesterday_ts = _yesterday_ts()

        sales = [
            FakeDoc('s1', {
                'shopId': 'shop1', 'totalAmount': 2000, 'amountPaid': 2000,
                'saleDate': yesterday_ts,
            }),
            FakeDoc('s2', {
                'shopId': 'shop1', 'totalAmount': 1000, 'amountPaid': 1000,
                'saleDate': yesterday_ts,
            }),
            # Vente d'aujourd'hui : doit être exclue.
            FakeDoc('s3', {
                'shopId': 'shop1', 'totalAmount': 5000, 'amountPaid': 5000,
                'saleDate': today_ts,
            }),
        ]
        produits = [
            FakeDoc('p1', {'shopId': 'shop1', 'name': 'Riz', 'quantity': 1, 'nbreCritique': 5}),
        ]
        db = FakeDB(collections={'sales': sales, 'produits': produits, 'customers': []})

        facts = morning_facts(db, 'shop1', {'name': 'Ma Boutique'})

        self.assertEqual(facts['shop_name'], 'Ma Boutique')
        self.assertEqual(facts['yesterday_count'], 2)
        self.assertEqual(facts['yesterday_revenue'], 3000.0)
        self.assertEqual(facts['ruptures_count'], 1)
        self.assertEqual(facts['ruptures_samples'], ['Riz'])

    def test_best_seller_computed_when_items_present(self):
        yesterday_ts = _yesterday_ts()

        sales = [
            FakeDoc('s1', {
                'shopId': 'shop1', 'totalAmount': 1000, 'amountPaid': 1000,
                'saleDate': yesterday_ts,
                'items': [
                    {'name': 'Riz', 'qty': 2},
                    {'name': 'Sucre', 'qty': 1},
                ],
            }),
            FakeDoc('s2', {
                'shopId': 'shop1', 'totalAmount': 500, 'amountPaid': 500,
                'saleDate': yesterday_ts,
                'items': [
                    {'name': 'Riz', 'qty': 3},
                ],
            }),
        ]
        db = FakeDB(collections={'sales': sales, 'produits': [], 'customers': []})

        facts = morning_facts(db, 'shop1', {'name': 'Ma Boutique'})

        self.assertEqual(facts.get('best_seller'), 'Riz')

    def test_best_seller_omitted_when_items_missing(self):
        yesterday_ts = _yesterday_ts()

        sales = [
            FakeDoc('s1', {
                'shopId': 'shop1', 'totalAmount': 1000, 'amountPaid': 1000,
                'saleDate': yesterday_ts,
            }),
        ]
        db = FakeDB(collections={'sales': sales, 'produits': [], 'customers': []})

        facts = morning_facts(db, 'shop1', {'name': 'Ma Boutique'})

        self.assertNotIn('best_seller', facts)

    def test_debts_keys_present_when_customers_have_debt(self):
        yesterday_ts = _yesterday_ts()
        sales = [
            FakeDoc('s1', {
                'shopId': 'shop1', 'totalAmount': 1000, 'amountPaid': 1000,
                'saleDate': yesterday_ts,
            }),
        ]
        customers = [
            FakeDoc('c1', {'shopId': 'shop1', 'totalDebt': 1500}),
            FakeDoc('c2', {'shopId': 'shop1', 'totalDebt': 600}),
            # Dette nulle -> ne compte pas dans debts_count/total.
            FakeDoc('c3', {'shopId': 'shop1', 'totalDebt': 0}),
        ]
        db = FakeDB(collections={'sales': sales, 'produits': [], 'customers': customers})

        facts = morning_facts(db, 'shop1', {'name': 'Ma Boutique'})

        self.assertEqual(facts['debts_count'], 2)
        self.assertEqual(facts['debts_total'], 2100.0)

    def test_debts_keys_omitted_when_customers_collection_empty(self):
        yesterday_ts = _yesterday_ts()
        sales = [
            FakeDoc('s1', {
                'shopId': 'shop1', 'totalAmount': 1000, 'amountPaid': 1000,
                'saleDate': yesterday_ts,
            }),
        ]
        db = FakeDB(collections={'sales': sales, 'produits': [], 'customers': []})

        facts = morning_facts(db, 'shop1', {'name': 'Ma Boutique'})

        self.assertNotIn('debts_count', facts)
        self.assertNotIn('debts_total', facts)

    def test_debts_keys_omitted_when_customers_collection_raises(self):
        yesterday_ts = _yesterday_ts()
        sales = [
            FakeDoc('s1', {
                'shopId': 'shop1', 'totalAmount': 1000, 'amountPaid': 1000,
                'saleDate': yesterday_ts,
            }),
        ]
        db = FakeDB(
            collections={'sales': sales, 'produits': []},
            raise_on={'customers'},
        )

        facts = morning_facts(db, 'shop1', {'name': 'Ma Boutique'})

        self.assertNotIn('debts_count', facts)
        self.assertNotIn('debts_total', facts)


class FirstNameTests(SimpleTestCase):
    def test_returns_first_token_of_name(self):
        db = FakeDB(users={'uid1': FakeDoc('uid1', {'name': 'Jean Dupont'})})

        self.assertEqual(first_name(db, 'uid1'), 'Jean')

    def test_returns_first_token_of_display_name_when_name_missing(self):
        db = FakeDB(users={'uid1': FakeDoc('uid1', {'displayName': 'Awa Traore'})})

        self.assertEqual(first_name(db, 'uid1'), 'Awa')

    def test_returns_empty_when_user_missing(self):
        db = FakeDB(users={})

        self.assertEqual(first_name(db, 'unknown'), '')
