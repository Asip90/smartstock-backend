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
