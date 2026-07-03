"""Tests de l'historique de notifications (écriture Firestore) et de l'envoi
ciblé admin. Utilise des mocks — ne touche jamais au vrai Firestore/FCM."""
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from billing import firebase_service
from billing import notif_engine
from billing import notifications as notif_admin


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


class EngineMirrorTest(SimpleTestCase):
    def test_compose_and_send_records_history(self):
        with patch.object(notif_engine.NotificationLog, 'recent_for',
                          return_value=([], None)), \
                patch.object(notif_engine.NotificationLog.objects, 'create'), \
                patch.object(notif_engine.ai_service, 'generate_message',
                             return_value=None), \
                patch.object(notif_engine.firebase_service, 'tokens_for_uid',
                             return_value=['tok']), \
                patch.object(notif_engine.firebase_service, 'send_push',
                             return_value=1), \
                patch.object(notif_engine.firebase_service,
                             'record_notification') as rec:
            notif_engine.compose_and_send(
                uid='uid9', kind='stock', facts={},
                fallback_title='Alerte stock', fallback_body='Produit bas')
        rec.assert_called_once()
        self.assertEqual(rec.call_args.args[0], 'uid9')
        self.assertEqual(rec.call_args.kwargs['title'], 'Alerte stock')
        self.assertEqual(rec.call_args.kwargs['body'], 'Produit bas')
        self.assertEqual(rec.call_args.kwargs['ntype'], 'stock')


class TargetedSendTest(SimpleTestCase):
    def test_uid_recipient_sends_and_records(self):
        with patch.object(notif_admin.firebase_service, '_ensure_init',
                          return_value=None), \
                patch.object(notif_admin.firebase_service, 'tokens_for_uid',
                             return_value=['a', 'b']) as toks, \
                patch.object(notif_admin.firebase_service, 'send_push',
                             return_value=2) as send, \
                patch.object(notif_admin.firebase_service,
                             'record_notification') as rec:
            count, uid = notif_admin.send_targeted_notification(
                'uid42', 'Bonjour', 'Message test')
        self.assertEqual((count, uid), (2, 'uid42'))
        toks.assert_called_once_with('uid42')
        send.assert_called_once()
        rec.assert_called_once()
        self.assertEqual(rec.call_args.kwargs['ntype'], 'admin')

    def test_email_recipient_is_resolved(self):
        fake_user = MagicMock(uid='resolved-uid')
        with patch.object(notif_admin.firebase_service, '_ensure_init',
                          return_value=None), \
                patch.object(notif_admin.fb_auth, 'get_user_by_email',
                             return_value=fake_user) as byemail, \
                patch.object(notif_admin.firebase_service, 'tokens_for_uid',
                             return_value=['t']), \
                patch.object(notif_admin.firebase_service, 'send_push',
                             return_value=1), \
                patch.object(notif_admin.firebase_service, 'record_notification'):
            count, uid = notif_admin.send_targeted_notification(
                'a@b.com', 'T', 'B')
        byemail.assert_called_once_with('a@b.com')
        self.assertEqual(uid, 'resolved-uid')
        self.assertEqual(count, 1)
