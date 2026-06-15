from unittest.mock import patch

from django.test import TestCase

from billing.models import NotificationLog
from billing.notif_engine import ANGLES, DEFAULT_ANGLES, compose_and_send, pick_angle


class ComposeAndSendTests(TestCase):
    @patch('billing.notif_engine.firebase_service.send_push')
    @patch('billing.notif_engine.firebase_service.tokens_for_uid')
    @patch('billing.notif_engine.ai_service.generate_message')
    def test_ai_success_uses_generated_body(self, mock_generate, mock_tokens, mock_send):
        mock_generate.return_value = 'Salut !'
        mock_tokens.return_value = ['tok1', 'tok2']
        mock_send.return_value = 2

        sent = compose_and_send(
            uid='user1', kind='morning', facts={'ventes': 3},
            fallback_title='Bonjour', fallback_body='Repli du matin')

        self.assertEqual(sent, 2)
        mock_send.assert_called_once()
        args, kwargs = mock_send.call_args
        # send_push(tokens, title, body, data)
        self.assertEqual(args[0], ['tok1', 'tok2'])
        self.assertEqual(args[1], 'Bonjour')
        self.assertEqual(args[2], 'Salut !')

        log = NotificationLog.objects.get(uid='user1', kind='morning')
        self.assertTrue(log.ai_used)
        self.assertEqual(log.body, 'Salut !')
        self.assertIn(log.angle, ANGLES['morning'])

    @patch('billing.notif_engine.firebase_service.send_push')
    @patch('billing.notif_engine.firebase_service.tokens_for_uid')
    @patch('billing.notif_engine.ai_service.generate_message')
    def test_ai_none_falls_back_to_template(self, mock_generate, mock_tokens, mock_send):
        mock_generate.return_value = None
        mock_tokens.return_value = ['tok1']
        mock_send.return_value = 1

        sent = compose_and_send(
            uid='user1', kind='evening', facts={'ca': 10000},
            fallback_title='Bilan du jour', fallback_body='Repli du soir')

        self.assertEqual(sent, 1)
        args, kwargs = mock_send.call_args
        self.assertEqual(args[2], 'Repli du soir')

        log = NotificationLog.objects.get(uid='user1', kind='evening')
        self.assertFalse(log.ai_used)
        self.assertEqual(log.body, 'Repli du soir')

    @patch('billing.notif_engine.firebase_service.send_push')
    @patch('billing.notif_engine.firebase_service.tokens_for_uid')
    @patch('billing.notif_engine.ai_service.generate_message')
    def test_notification_log_fields(self, mock_generate, mock_tokens, mock_send):
        mock_generate.return_value = 'Message IA'
        mock_tokens.return_value = []
        mock_send.return_value = 0

        compose_and_send(
            uid='shop-42', kind='stock', facts={'rupture': 'Riz'},
            fallback_title='Alerte stock', fallback_body='Repli stock')

        log = NotificationLog.objects.get(uid='shop-42', kind='stock')
        self.assertEqual(log.uid, 'shop-42')
        self.assertEqual(log.kind, 'stock')
        self.assertEqual(log.title, 'Alerte stock')
        self.assertIn(log.angle, ANGLES['stock'])

    @patch('billing.notif_engine.firebase_service.send_push')
    @patch('billing.notif_engine.firebase_service.tokens_for_uid')
    @patch('billing.notif_engine.ai_service.generate_message')
    def test_push_data_defaults_to_type_kind(self, mock_generate, mock_tokens, mock_send):
        mock_generate.return_value = 'Message IA'
        mock_tokens.return_value = ['tok1']
        mock_send.return_value = 1

        compose_and_send(
            uid='user1', kind='stock', facts={},
            fallback_title='Alerte stock', fallback_body='Repli stock')

        args, kwargs = mock_send.call_args
        data = args[3]
        self.assertEqual(data.get('type'), 'stock')

    @patch('billing.notif_engine.firebase_service.send_push')
    @patch('billing.notif_engine.firebase_service.tokens_for_uid')
    @patch('billing.notif_engine.ai_service.generate_message')
    def test_push_data_custom_is_passed_through(self, mock_generate, mock_tokens, mock_send):
        mock_generate.return_value = 'Message IA'
        mock_tokens.return_value = ['tok1']
        mock_send.return_value = 1

        compose_and_send(
            uid='user1', kind='stock', facts={},
            fallback_title='Alerte stock', fallback_body='Repli stock',
            push_data={'type': 'stock', 'product': 'Riz'})

        args, kwargs = mock_send.call_args
        data = args[3]
        self.assertEqual(data, {'type': 'stock', 'product': 'Riz'})


class PickAngleTests(TestCase):
    def test_never_returns_last_angle_morning(self):
        for _ in range(50):
            angle = pick_angle('morning', 'motivant')
            self.assertNotEqual(angle, 'motivant')
            self.assertIn(angle, ANGLES['morning'])

    def test_unknown_kind_returns_default_angle(self):
        for _ in range(20):
            angle = pick_angle('unknown_kind', None)
            self.assertIn(angle, DEFAULT_ANGLES)

    def test_last_angle_none_returns_valid_angle(self):
        angle = pick_angle('stock', None)
        self.assertIn(angle, ANGLES['stock'])
