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
