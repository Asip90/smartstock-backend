from unittest.mock import MagicMock, patch

from django.test import TestCase

from storefront.firebase_read import (
    _serialize_product,
    _shop_is_pro,
    _slugify,
    get_public_products_by_ids,
    get_shop_owner_uid,
)


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
