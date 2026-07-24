from unittest.mock import MagicMock, patch

from django.test import Client, TestCase, override_settings

_SHOP = {
    'id': 's1', 'name': 'Ma Boutique', 'publicSlug': 'ma-boutique',
    'storefrontEnabled': True, 'currency': 'XOF', 'heroImageUrl': None,
    'heroTitle_fr': None, 'heroTitle_en': None, 'heroSubtitle_fr': None,
    'heroSubtitle_en': None, 'aboutText_fr': None, 'aboutText_en': None,
    'seoDescription_fr': None, 'seoDescription_en': None,
    'whatsappNumber': '2290100000000', 'allowContact': True,
    'allowCartOrder': True, 'allowOnlinePayment': False,
    'primaryColorHex': '#1565C0', 'isPro': True,
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
    @patch('storefront.firebase_read.fb.db')
    @patch('storefront.views.fb_read.get_shop_by_slug')
    def test_checkout_cree_la_commande_et_vide_le_panier(
        self, mock_shop, mock_db, mock_notify,
    ):
        # `storefront.orders` et `storefront.firebase_read` importent le MÊME
        # module `billing.firebase_service` (aliasé `fb`) — un seul patch de
        # `fb.db` couvre donc les DEUX call sites (lecture produit ET écriture
        # storeOrders), qu'il faut router selon la collection demandée.
        mock_shop.return_value = _SHOP
        doc = MagicMock()
        doc.exists = True
        doc.id = 'p1'
        doc.to_dict.return_value = {'shopId': 's1', 'name': 'Sac', 'price': 1000, 'quantity': 5}
        produits_collection = MagicMock()
        produits_collection.document.return_value.get.return_value = doc

        mock_doc_ref = MagicMock()
        mock_doc_ref.id = 'order123'
        orders_collection = MagicMock()
        orders_collection.add.return_value = (None, mock_doc_ref)

        def collection(name):
            return {'produits': produits_collection, 'storeOrders': orders_collection}[name]

        mock_db.return_value.collection.side_effect = collection

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
        response = self.client.get('/commande')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'plus disponible', status_code=200)

    @patch('storefront.views.notify.notify_new_order')
    @patch('storefront.views.fedapay.create_checkout')
    @patch('storefront.firebase_read.fb.db')
    @patch('storefront.views.fb_read.get_shop_by_slug')
    def test_checkout_paiement_en_ligne_redirige_vers_fedapay(
        self, mock_shop, mock_db, mock_create_checkout, mock_notify,
    ):
        mock_shop.return_value = {**_SHOP, 'allowOnlinePayment': True}
        doc = MagicMock()
        doc.exists = True
        doc.id = 'p1'
        doc.to_dict.return_value = {'shopId': 's1', 'name': 'Sac', 'price': 1000, 'quantity': 5}
        produits_collection = MagicMock()
        produits_collection.document.return_value.get.return_value = doc

        mock_doc_ref = MagicMock()
        mock_doc_ref.id = 'order123'
        orders_collection = MagicMock()
        orders_collection.add.return_value = (None, mock_doc_ref)

        def collection(name):
            return {'produits': produits_collection, 'storeOrders': orders_collection}[name]

        mock_db.return_value.collection.side_effect = collection
        mock_create_checkout.return_value = {
            'fedapay_id': 'fp_tx_1', 'token': 'tok', 'url': 'https://sandbox-checkout.fedapay.com/tok',
        }

        self.client.post('/panier/ajouter', {'product_id': 'p1', 'qty': 2})
        response = self.client.post('/commande', {
            'customer_name': 'Awa', 'customer_phone': '229010000',
            'customer_address': 'Cotonou', 'customer_email': 'awa@example.com',
            'payment_mode': 'online',
        })

        self.assertRedirects(
            response, 'https://sandbox-checkout.fedapay.com/tok',
            fetch_redirect_response=False,
        )
        mock_create_checkout.assert_called_once()
        self.assertEqual(mock_create_checkout.call_args.kwargs['currency'], 'XOF')
        self.assertEqual(mock_create_checkout.call_args.kwargs['amount'], 2000)
        orders_collection.document.return_value.update.assert_called_once_with(
            {'paymentRef': 'fp_tx_1'})
        self.assertEqual(self.client.session.get('cart', {}), {})

    @patch('storefront.views.fb_read.get_shop_by_slug')
    def test_checkout_paiement_en_ligne_refuse_si_allowOnlinePayment_faux(self, mock_shop):
        # allowOnlinePayment=False sur la boutique : le champ payment_mode=online
        # envoyé par un client malveillant est ignoré, repli cash_on_delivery
        # silencieux (jamais confiance au formulaire pour un choix qui a un
        # impact financier).
        mock_shop.return_value = {**_SHOP, 'allowOnlinePayment': False}
        response = self.client.post('/commande', {'payment_mode': 'online'})
        # cart vide => redirigé vers le panier, AVANT même la logique de paiement
        self.assertRedirects(response, '/panier')

    @patch('storefront.firebase_read.fb.db')
    @patch('storefront.views.fb_read.get_shop_by_slug')
    def test_checkout_paiement_en_ligne_email_manquant(self, mock_shop, mock_db):
        mock_shop.return_value = {**_SHOP, 'allowOnlinePayment': True}
        doc = MagicMock()
        doc.exists = True
        doc.id = 'p1'
        doc.to_dict.return_value = {'shopId': 's1', 'name': 'Sac', 'price': 1000, 'quantity': 5}
        mock_db.return_value.collection.return_value.document.return_value.get.return_value = doc

        self.client.post('/panier/ajouter', {'product_id': 'p1', 'qty': 1})
        response = self.client.post('/commande', {
            'customer_name': 'Awa', 'customer_phone': '229010000',
            'customer_address': 'Cotonou', 'payment_mode': 'online',
        })

        self.assertRedirects(response, '/commande')
        # panier NON vidé : la commande n'a pas été créée, l'utilisateur peut corriger.
        self.assertEqual(self.client.session.get('cart', {}), {'p1': 1})

    @patch('storefront.views.fb_read.get_shop_by_slug')
    def test_payment_return_affiche_un_message_generique(self, mock_shop):
        mock_shop.return_value = _SHOP
        response = self.client.get('/paiement/retour')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Commande envoyée')
