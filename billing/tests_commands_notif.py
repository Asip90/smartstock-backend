"""Tests légers pour les commandes cron de notifications (matin/soir/stock).

Vérifie que chaque commande :
- calcule les bons faits via ``notif_facts`` ;
- détermine correctement les destinataires (propriétaire + membres) selon
  leurs réglages de notification ;
- appelle ``notif_engine.compose_and_send`` avec le bon ``kind`` et le bon
  ``push_data['type']`` (la valeur historique attendue par l'app) ;
- passe un ``fallback_body`` templaté identique au comportement existant
  (IA désactivée).

Utilise un faux client Firestore (mêmes classes que ``tests_notif_facts``)
pour ne jamais toucher au vrai Firestore, et patche
``notif_engine.compose_and_send`` pour ne jamais envoyer de vrai push.
"""
from datetime import datetime, time, timedelta
from unittest.mock import patch

from django.core.management import call_command
from django.test import SimpleTestCase
from django.utils import timezone

from billing.tests_notif_facts import FakeDB, FakeDoc


def _today_ts():
    now = timezone.localtime()
    start_of_today = timezone.make_aware(datetime.combine(now.date(), time.min))
    return start_of_today + timedelta(hours=10)


def _yesterday_ts():
    now = timezone.localtime()
    start_of_today = timezone.make_aware(datetime.combine(now.date(), time.min))
    return start_of_today - timedelta(hours=2)


class _FakeMembers:
    """Sous-collection `members` d'une boutique : `.stream()` -> docs."""

    def __init__(self, docs):
        self._docs = docs

    def stream(self):
        return iter(self._docs)


class _FakeShopDocRef:
    def __init__(self, members_docs):
        self._members_docs = members_docs

    def collection(self, name):
        assert name == 'members'
        return _FakeMembers(self._members_docs)


class FakeDBWithShops(FakeDB):
    """Étend FakeDB avec `shops` (et `.document(id).collection('members')`)."""

    def __init__(self, shops, members_by_shop=None, **kwargs):
        super().__init__(**kwargs)
        self._shops = shops
        self._members_by_shop = members_by_shop or {}

    def collection(self, name):
        if name == 'shops':
            query = super().collection('shops') if 'shops' in self._collections else None
            shops_query = _ShopsQuery(self._shops, self._members_by_shop)
            return shops_query
        return super().collection(name)


class _ShopsQuery:
    def __init__(self, shops, members_by_shop):
        self._shops = shops
        self._members_by_shop = members_by_shop

    def stream(self):
        return iter(self._shops)

    def document(self, doc_id):
        return _FakeShopDocRef(self._members_by_shop.get(doc_id, []))


class SendMorningBriefingTests(SimpleTestCase):
    def _build_db(self):
        yesterday_ts = _yesterday_ts()
        shops = [FakeDoc('shop1', {'name': 'Ma Boutique', 'ownerId': 'owner1'})]
        sales = [
            FakeDoc('s1', {
                'shopId': 'shop1', 'totalAmount': 2000, 'amountPaid': 2000,
                'saleDate': yesterday_ts,
            }),
        ]
        produits = [
            FakeDoc('p1', {'shopId': 'shop1', 'name': 'Riz', 'quantity': 1, 'nbreCritique': 5}),
        ]
        customers = [
            FakeDoc('c1', {'shopId': 'shop1', 'totalDebt': 1500}),
        ]
        db = FakeDBWithShops(
            shops=shops,
            members_by_shop={},
            collections={'sales': sales, 'produits': produits, 'customers': customers},
            users={'owner1': FakeDoc('owner1', {'name': 'Awa Traore'})},
        )
        return db

    @patch('billing.management.commands.send_morning_briefing.notif_engine.compose_and_send')
    @patch('billing.management.commands.send_morning_briefing.fb.notif_settings')
    @patch('billing.management.commands.send_morning_briefing.fb.db')
    def test_sends_morning_briefing_with_expected_kind_and_push_data(
            self, mock_db, mock_settings, mock_compose):
        mock_db.return_value = self._build_db()
        mock_settings.return_value = {'notif_morning_briefing': True}
        mock_compose.return_value = 1

        call_command('send_morning_briefing')

        mock_compose.assert_called_once()
        _, kwargs = mock_compose.call_args
        self.assertEqual(kwargs['uid'], 'owner1')
        self.assertEqual(kwargs['kind'], 'morning')
        self.assertEqual(kwargs['push_data'], {'type': 'morning_briefing', 'shopId': 'shop1'})
        self.assertEqual(kwargs['fallback_title'], 'Bonjour — Ma Boutique')
        body = kwargs['fallback_body']
        self.assertIn('hier', body)
        self.assertIn('rupture', body)
        self.assertIn('relancer', body)
        self.assertEqual(kwargs['facts']['first_name'], 'Awa')

    @patch('billing.management.commands.send_morning_briefing.notif_engine.compose_and_send')
    @patch('billing.management.commands.send_morning_briefing.fb.notif_settings')
    @patch('billing.management.commands.send_morning_briefing.fb.db')
    def test_skips_recipient_with_setting_disabled(
            self, mock_db, mock_settings, mock_compose):
        mock_db.return_value = self._build_db()
        mock_settings.return_value = {'notif_morning_briefing': False}

        call_command('send_morning_briefing')

        mock_compose.assert_not_called()

    @patch('billing.management.commands.send_morning_briefing.notif_engine.compose_and_send')
    @patch('billing.management.commands.send_morning_briefing.fb.notif_settings')
    @patch('billing.management.commands.send_morning_briefing.fb.db')
    def test_skips_shop_with_nothing_notable(
            self, mock_db, mock_settings, mock_compose):
        shops = [FakeDoc('shop1', {'name': 'Boutique calme', 'ownerId': 'owner1'})]
        db = FakeDBWithShops(
            shops=shops,
            members_by_shop={},
            collections={'sales': [], 'produits': [], 'customers': []},
            users={'owner1': FakeDoc('owner1', {'name': 'Awa Traore'})},
        )
        mock_db.return_value = db
        mock_settings.return_value = {'notif_morning_briefing': True}

        call_command('send_morning_briefing')

        mock_compose.assert_not_called()


class SendDailySummaryTests(SimpleTestCase):
    @patch('billing.management.commands.send_daily_summary.notif_engine.compose_and_send')
    @patch('billing.management.commands.send_daily_summary.fb.notif_settings')
    @patch('billing.management.commands.send_daily_summary.fb.db')
    def test_sends_evening_summary_with_expected_kind_and_push_data(
            self, mock_db, mock_settings, mock_compose):
        today_ts = _today_ts()
        shops = [FakeDoc('shop1', {'name': 'Ma Boutique', 'ownerId': 'owner1'})]
        sales = [
            FakeDoc('s1', {
                'shopId': 'shop1', 'totalAmount': 1000, 'amountPaid': 1000,
                'saleDate': today_ts,
            }),
            FakeDoc('s2', {
                'shopId': 'shop1', 'totalAmount': 500, 'amountPaid': 200,
                'saleDate': today_ts,
            }),
        ]
        db = FakeDBWithShops(
            shops=shops,
            members_by_shop={},
            collections={'sales': sales},
            users={'owner1': FakeDoc('owner1', {'name': 'Jean Dupont'})},
        )
        mock_db.return_value = db
        mock_settings.return_value = {'notif_daily_summary': True}
        mock_compose.return_value = 1

        call_command('send_daily_summary')

        mock_compose.assert_called_once()
        _, kwargs = mock_compose.call_args
        self.assertEqual(kwargs['uid'], 'owner1')
        self.assertEqual(kwargs['kind'], 'evening')
        self.assertEqual(kwargs['push_data'], {'type': 'daily_summary', 'shopId': 'shop1'})
        self.assertEqual(kwargs['fallback_title'], 'Bilan du jour — Ma Boutique')
        body = kwargs['fallback_body']
        self.assertIn('2 vente(s)', body)
        self.assertIn('CA 1 500 FCFA', body)
        self.assertIn('encaissé 1 200', body)
        self.assertIn('à crédit 300', body)
        self.assertEqual(kwargs['facts']['first_name'], 'Jean')

    @patch('billing.management.commands.send_daily_summary.notif_engine.compose_and_send')
    @patch('billing.management.commands.send_daily_summary.fb.notif_settings')
    @patch('billing.management.commands.send_daily_summary.fb.db')
    def test_skips_recipient_with_setting_disabled(
            self, mock_db, mock_settings, mock_compose):
        today_ts = _today_ts()
        shops = [FakeDoc('shop1', {'name': 'Ma Boutique', 'ownerId': 'owner1'})]
        sales = [
            FakeDoc('s1', {
                'shopId': 'shop1', 'totalAmount': 1000, 'amountPaid': 1000,
                'saleDate': today_ts,
            }),
        ]
        db = FakeDBWithShops(
            shops=shops, members_by_shop={}, collections={'sales': sales}, users={},
        )
        mock_db.return_value = db
        mock_settings.return_value = {'notif_daily_summary': False}

        call_command('send_daily_summary')

        mock_compose.assert_not_called()

    @patch('billing.management.commands.send_daily_summary.notif_engine.compose_and_send')
    @patch('billing.management.commands.send_daily_summary.fb.notif_settings')
    @patch('billing.management.commands.send_daily_summary.fb.db')
    def test_skips_shop_with_no_sales(
            self, mock_db, mock_settings, mock_compose):
        shops = [FakeDoc('shop1', {'name': 'Ma Boutique', 'ownerId': 'owner1'})]
        db = FakeDBWithShops(
            shops=shops, members_by_shop={}, collections={'sales': []}, users={},
        )
        mock_db.return_value = db
        mock_settings.return_value = {'notif_daily_summary': True}

        call_command('send_daily_summary')

        mock_compose.assert_not_called()


class SendStockAlertsTests(SimpleTestCase):
    @patch('billing.management.commands.send_stock_alerts.notif_engine.compose_and_send')
    @patch('billing.management.commands.send_stock_alerts.fb.notif_settings')
    @patch('billing.management.commands.send_stock_alerts.fb.db')
    def test_sends_stock_alert_with_expected_kind_and_push_data(
            self, mock_db, mock_settings, mock_compose):
        shops = [FakeDoc('shop1', {'name': 'Ma Boutique', 'ownerId': 'owner1'})]
        produits = [
            FakeDoc('p1', {'shopId': 'shop1', 'name': 'Riz', 'quantity': 1, 'nbreCritique': 5}),
            FakeDoc('p2', {'shopId': 'shop1', 'name': 'Sucre', 'quantity': 0, 'nbreCritique': 5}),
        ]
        db = FakeDBWithShops(
            shops=shops,
            members_by_shop={},
            collections={'produits': produits},
            users={'owner1': FakeDoc('owner1', {'name': 'Jean Dupont'})},
        )
        mock_db.return_value = db
        mock_settings.return_value = {'notif_critical_stock': True}
        mock_compose.return_value = 1

        call_command('send_stock_alerts')

        mock_compose.assert_called_once()
        _, kwargs = mock_compose.call_args
        self.assertEqual(kwargs['uid'], 'owner1')
        self.assertEqual(kwargs['kind'], 'stock')
        self.assertEqual(kwargs['push_data'], {'type': 'critical_stock', 'shopId': 'shop1'})
        self.assertEqual(kwargs['fallback_title'], 'Stock critique — Ma Boutique')
        body = kwargs['fallback_body']
        self.assertIn('2 produit(s) en stock faible', body)
        self.assertEqual(kwargs['facts']['first_name'], 'Jean')

    @patch('billing.management.commands.send_stock_alerts.notif_engine.compose_and_send')
    @patch('billing.management.commands.send_stock_alerts.fb.notif_settings')
    @patch('billing.management.commands.send_stock_alerts.fb.db')
    def test_skips_shop_with_no_low_stock(
            self, mock_db, mock_settings, mock_compose):
        shops = [FakeDoc('shop1', {'name': 'Ma Boutique', 'ownerId': 'owner1'})]
        produits = [
            FakeDoc('p1', {'shopId': 'shop1', 'name': 'Riz', 'quantity': 10, 'nbreCritique': 5}),
        ]
        db = FakeDBWithShops(
            shops=shops, members_by_shop={}, collections={'produits': produits}, users={},
        )
        mock_db.return_value = db
        mock_settings.return_value = {'notif_critical_stock': True}

        call_command('send_stock_alerts')

        mock_compose.assert_not_called()

    @patch('billing.management.commands.send_stock_alerts.notif_engine.compose_and_send')
    @patch('billing.management.commands.send_stock_alerts.fb.notif_settings')
    @patch('billing.management.commands.send_stock_alerts.fb.db')
    def test_skips_recipient_with_setting_disabled(
            self, mock_db, mock_settings, mock_compose):
        shops = [FakeDoc('shop1', {'name': 'Ma Boutique', 'ownerId': 'owner1'})]
        produits = [
            FakeDoc('p1', {'shopId': 'shop1', 'name': 'Riz', 'quantity': 1, 'nbreCritique': 5}),
        ]
        db = FakeDBWithShops(
            shops=shops, members_by_shop={}, collections={'produits': produits}, users={},
        )
        mock_db.return_value = db
        mock_settings.return_value = {'notif_critical_stock': False}

        call_command('send_stock_alerts')

        mock_compose.assert_not_called()
