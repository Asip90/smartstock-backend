from unittest.mock import patch, Mock

import requests
from django.test import TestCase

from billing.ai_service import generate_message
from billing.models import AIConfig


def _enable_config(**overrides):
    cfg = AIConfig.get_solo()
    cfg.enabled = True
    cfg.api_key = 'test-api-key'
    cfg.provider = 'mistral'
    cfg.model = 'mistral-small-latest'
    cfg.temperature = 0.9
    cfg.max_tokens = 120
    for key, value in overrides.items():
        setattr(cfg, key, value)
    cfg.save()
    return cfg


def _mock_response(content='Bonjour, voici votre résumé du jour.'):
    resp = Mock()
    resp.raise_for_status = Mock()
    resp.json.return_value = {
        'choices': [{'message': {'content': content}}],
    }
    return resp


class GenerateMessageTests(TestCase):
    @patch('billing.ai_service.requests.post')
    def test_happy_path_returns_cleaned_content(self, mock_post):
        _enable_config()
        mock_post.return_value = _mock_response('"Belle journée : 12 ventes pour 45 000 FCFA."')

        result = generate_message(
            kind='morning',
            facts={'ventes': 12, 'total': '45 000 FCFA'},
            recent=[],
            angle='positif',
        )

        self.assertEqual(result, 'Belle journée : 12 ventes pour 45 000 FCFA.')
        mock_post.assert_called_once()

    @patch('billing.ai_service.requests.post')
    def test_ai_disabled_returns_none(self, mock_post):
        _enable_config(enabled=False)

        result = generate_message(kind='morning', facts={}, recent=[], angle='positif')

        self.assertIsNone(result)
        mock_post.assert_not_called()

    @patch('billing.ai_service.requests.post')
    def test_missing_api_key_returns_none(self, mock_post):
        _enable_config(api_key='')

        result = generate_message(kind='morning', facts={}, recent=[], angle='positif')

        self.assertIsNone(result)
        mock_post.assert_not_called()

    @patch('billing.ai_service.requests.post')
    def test_channel_disabled_returns_none(self, mock_post):
        _enable_config(ai_stock=False)

        result = generate_message(kind='stock', facts={}, recent=[], angle='alerte')

        self.assertIsNone(result)
        mock_post.assert_not_called()

    @patch('billing.ai_service.requests.post')
    def test_http_error_returns_none(self, mock_post):
        _enable_config()
        resp = Mock()
        resp.raise_for_status.side_effect = requests.HTTPError('boom')
        mock_post.return_value = resp

        result = generate_message(kind='morning', facts={}, recent=[], angle='positif')

        self.assertIsNone(result)

    @patch('billing.ai_service.requests.post')
    def test_timeout_returns_none(self, mock_post):
        _enable_config()
        mock_post.side_effect = requests.Timeout('timeout')

        result = generate_message(kind='morning', facts={}, recent=[], angle='positif')

        self.assertIsNone(result)

    @patch('billing.ai_service.requests.post')
    def test_malformed_json_returns_none(self, mock_post):
        _enable_config()
        resp = Mock()
        resp.raise_for_status = Mock()
        resp.json.return_value = {'unexpected': 'shape'}
        mock_post.return_value = resp

        result = generate_message(kind='morning', facts={}, recent=[], angle='positif')

        self.assertIsNone(result)

    @patch('billing.ai_service.requests.post')
    def test_provider_routing_mistral(self, mock_post):
        _enable_config(provider='mistral')
        mock_post.return_value = _mock_response('Tout va bien.')

        generate_message(kind='morning', facts={}, recent=[], angle='positif')

        called_url = mock_post.call_args[0][0]
        self.assertEqual(called_url, 'https://api.mistral.ai/v1/chat/completions')

    @patch('billing.ai_service.requests.post')
    def test_provider_routing_openrouter(self, mock_post):
        _enable_config(provider='openrouter')
        mock_post.return_value = _mock_response('Tout va bien.')

        generate_message(kind='morning', facts={}, recent=[], angle='positif')

        called_url = mock_post.call_args[0][0]
        self.assertEqual(called_url, 'https://openrouter.ai/api/v1/chat/completions')

    @patch('billing.ai_service.requests.post')
    def test_unknown_provider_returns_none(self, mock_post):
        _enable_config(provider='unknown-provider')

        result = generate_message(kind='morning', facts={}, recent=[], angle='positif')

        self.assertIsNone(result)
        mock_post.assert_not_called()
