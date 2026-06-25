"""Tests de l'endpoint `/api/notify-owner` (rappel propriétaire par un cogérant)
et de `firebase_service.mirror_pro_to_shops`.

Utilise de faux objets Firestore minimaux (mêmes principes que les autres tests
de ce module) pour ne jamais toucher au vrai Firestore.
"""
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

UID = 'firebase-uid-comanager'
OWNER_UID = 'firebase-uid-owner'
SHOP_ID = 'shop-123'
AUTH = {'HTTP_AUTHORIZATION': 'Bearer fake-token'}


class _FakeDocSnapshot:
    def __init__(self, exists, data=None):
        self.exists = exists
        self._data = data or {}

    def to_dict(self):
        return dict(self._data)


class _FakeMembersCollection:
    def __init__(self, member_exists):
        self._member_exists = member_exists

    def document(self, doc_id):
        snap = _FakeDocSnapshot(self._member_exists)
        ref = MagicMock()
        ref.get.return_value = snap
        return ref


class _FakeShopDocRef:
    def __init__(self, shop_exists, shop_data, member_exists):
        self._shop_exists = shop_exists
        self._shop_data = shop_data
        self._member_exists = member_exists

    def get(self):
        return _FakeDocSnapshot(self._shop_exists, self._shop_data)

    def collection(self, name):
        assert name == 'members'
        return _FakeMembersCollection(self._member_exists)


class _FakeShopsCollection:
    def __init__(self, shop_exists, shop_data, member_exists):
        self._shop_exists = shop_exists
        self._shop_data = shop_data
        self._member_exists = member_exists

    def document(self, doc_id):
        return _FakeShopDocRef(self._shop_exists, self._shop_data, self._member_exists)


class _FakeDB:
    def __init__(self, shop_exists=True, shop_data=None, member_exists=True):
        self._shop_exists = shop_exists
        self._shop_data = shop_data
        self._member_exists = member_exists

    def collection(self, name):
        assert name == 'shops'
        return _FakeShopsCollection(self._shop_exists, self._shop_data, self._member_exists)


class NotifyOwnerTests(SimpleTestCase):
    def _patch_auth(self, uid=UID):
        p = patch('billing.firebase_service.verify_token', return_value=(uid, 'x@example.com'))
        p.start()
        self.addCleanup(p.stop)

    def test_member_actif_envoie_au_proprietaire(self):
        self._patch_auth()
        fake_db = _FakeDB(shop_data={'ownerId': OWNER_UID, 'name': 'Ma Boutique'},
                          member_exists=True)
        with patch('billing.firebase_service.db', return_value=fake_db), \
             patch('billing.firebase_service.tokens_for_uid', return_value=['tok1', 'tok2']) as m_tokens, \
             patch('billing.firebase_service.send_push', return_value=2) as m_push:
            resp = self.client.post('/api/notify-owner', {'shopId': SHOP_ID},
                                    content_type='application/json', **AUTH)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), {'ok': True, 'sent': 2})
        m_tokens.assert_called_once_with(OWNER_UID)
        m_push.assert_called_once()
        args, kwargs = m_push.call_args
        self.assertEqual(args[0], ['tok1', 'tok2'])
        self.assertEqual(kwargs['data'], {'type': 'subscription', 'stage': 'owner_reminder'})
        self.assertIn('Ma Boutique', args[2])

    def test_non_membre_recoit_403(self):
        self._patch_auth()
        fake_db = _FakeDB(shop_data={'ownerId': OWNER_UID, 'name': 'Ma Boutique'},
                          member_exists=False)
        with patch('billing.firebase_service.db', return_value=fake_db), \
             patch('billing.firebase_service.tokens_for_uid') as m_tokens, \
             patch('billing.firebase_service.send_push') as m_push:
            resp = self.client.post('/api/notify-owner', {'shopId': SHOP_ID},
                                    content_type='application/json', **AUTH)
        self.assertEqual(resp.status_code, 403)
        m_tokens.assert_not_called()
        m_push.assert_not_called()

    def test_shop_id_manquant_400(self):
        self._patch_auth()
        resp = self.client.post('/api/notify-owner', {},
                                content_type='application/json', **AUTH)
        self.assertEqual(resp.status_code, 400)

    def test_sans_auth_401(self):
        resp = self.client.post('/api/notify-owner', {'shopId': SHOP_ID},
                                content_type='application/json')
        self.assertEqual(resp.status_code, 401)


class MirrorProToShopsTests(SimpleTestCase):
    def test_ecrit_proUntil_sur_les_boutiques_du_proprietaire(self):
        from billing import firebase_service as fb

        shop_a = _FakeDocSnapshot(True, {'ownerId': OWNER_UID})
        shop_a.id = 'shop-a'
        shop_b = _FakeDocSnapshot(True, {'ownerId': OWNER_UID})
        shop_b.id = 'shop-b'

        query = MagicMock()
        query.stream.return_value = [shop_a, shop_b]

        doc_refs = {}

        def _document(doc_id):
            ref = doc_refs.setdefault(doc_id, MagicMock())
            return ref

        shops_collection = MagicMock()
        shops_collection.where.return_value = query
        shops_collection.document.side_effect = _document

        fake_db = MagicMock()
        fake_db.collection.return_value = shops_collection

        with patch('billing.firebase_service._ensure_init'), \
             patch('billing.firebase_service._db', fake_db):
            fb.mirror_pro_to_shops(OWNER_UID, 'PERIOD_END_SENTINEL')

        shops_collection.where.assert_called_once_with('ownerId', '==', OWNER_UID)
        doc_refs['shop-a'].set.assert_called_once_with(
            {'proUntil': 'PERIOD_END_SENTINEL'}, merge=True)
        doc_refs['shop-b'].set.assert_called_once_with(
            {'proUntil': 'PERIOD_END_SENTINEL'}, merge=True)
