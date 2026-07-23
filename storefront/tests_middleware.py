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
