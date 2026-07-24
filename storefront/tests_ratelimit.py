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
