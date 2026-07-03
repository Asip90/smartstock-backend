"""Tests de l'historique de notifications (écriture Firestore) et de l'envoi
ciblé admin. Utilise des mocks — ne touche jamais au vrai Firestore/FCM."""
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from billing import firebase_service


class RecordNotificationTest(SimpleTestCase):
    def test_writes_doc_with_expected_shape(self):
        fake_db = MagicMock()
        with patch.object(firebase_service, '_ensure_init', lambda: None), \
                patch.object(firebase_service, '_db', fake_db):
            firebase_service.record_notification(
                'uid1', title='Titre', body='Corps',
                data={'url': 'https://x', 'n': 3}, ntype='stock')
        add = (fake_db.collection.return_value
               .document.return_value
               .collection.return_value.add)
        fake_db.collection.assert_any_call('users')
        add.assert_called_once()
        payload = add.call_args.args[0]
        self.assertEqual(payload['title'], 'Titre')
        self.assertEqual(payload['body'], 'Corps')
        self.assertEqual(payload['type'], 'stock')
        self.assertEqual(payload['read'], False)
        self.assertEqual(payload['data'], {'url': 'https://x', 'n': '3'})
