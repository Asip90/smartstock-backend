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
