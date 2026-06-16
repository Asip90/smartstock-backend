"""Tests du bilan hebdomadaire (faits + commande cron).

Vérifie que :
- ``weekly_facts`` agrège correctement la semaine en cours vs la précédente
  (fenêtres glissantes de 7 jours), calcule la croissance et le meilleur jour ;
- la commande ``send_weekly_recap`` en mode dry-run (défaut) N'ENVOIE RIEN
  (``compose_and_send`` jamais appelé), et envoie en mode ``--commit``.

Réutilise les faux clients Firestore des autres tests de notifications afin de
ne jamais toucher au vrai Firestore.
"""
from datetime import datetime, time, timedelta
from unittest.mock import patch

from django.core.management import call_command
from django.test import SimpleTestCase
from django.utils import timezone

from billing.notif_facts import weekly_facts
from billing.tests_notif_facts import FakeDB, FakeDoc
from billing.tests_commands_notif import FakeDBWithShops


def _days_ago_ts(days, hour=10):
    """Horodatage à ``days`` jours dans le passé, à ``hour`` heures."""
    now = timezone.localtime()
    start_of_today = timezone.make_aware(datetime.combine(now.date(), time.min))
    return start_of_today - timedelta(days=days) + timedelta(hours=hour)


class WeeklyFactsTests(SimpleTestCase):
    def test_week_over_week_comparison_and_best_day(self):
        sales = [
            # Semaine en cours.
            FakeDoc('a1', {'shopId': 'shop1', 'totalAmount': 1000,
                           'saleDate': _days_ago_ts(0)}),
            FakeDoc('a2', {'shopId': 'shop1', 'totalAmount': 2000,
                           'saleDate': _days_ago_ts(1)}),
            FakeDoc('a3', {'shopId': 'shop1', 'totalAmount': 1000,
                           'saleDate': _days_ago_ts(1)}),  # J-1 = meilleur jour
            # Semaine précédente (J-7 .. J-13).
            FakeDoc('b1', {'shopId': 'shop1', 'totalAmount': 1500,
                           'saleDate': _days_ago_ts(8)}),
            FakeDoc('b2', {'shopId': 'shop1', 'totalAmount': 500,
                           'saleDate': _days_ago_ts(9)}),
            # Hors fenêtre (J-20) : exclu.
            FakeDoc('c1', {'shopId': 'shop1', 'totalAmount': 9999,
                           'saleDate': _days_ago_ts(20)}),
            # Autre boutique : exclu.
            FakeDoc('d1', {'shopId': 'shop2', 'totalAmount': 7777,
                           'saleDate': _days_ago_ts(0)}),
        ]
        db = FakeDB(collections={'sales': sales})

        facts = weekly_facts(db, 'shop1', {'name': 'Ma Boutique'})

        self.assertEqual(facts['shop_name'], 'Ma Boutique')
        self.assertEqual(facts['count'], 3)
        self.assertEqual(facts['revenue'], 4000.0)
        self.assertEqual(facts['prev_revenue'], 2000.0)
        # (4000 - 2000) / 2000 * 100 = 100%
        self.assertEqual(facts['growth'], 100.0)
        # Meilleur jour : J-1 avec 3000.
        self.assertEqual(facts['best_day'], _days_ago_ts(1).date().isoformat())
        self.assertEqual(facts['best_day_revenue'], 3000.0)

    def test_no_sales_is_graceful(self):
        db = FakeDB(collections={'sales': []})

        facts = weekly_facts(db, 'shop1', {'name': 'Ma Boutique'})

        self.assertEqual(facts['count'], 0)
        self.assertEqual(facts['revenue'], 0.0)
        self.assertEqual(facts['prev_revenue'], 0.0)
        self.assertIsNone(facts['growth'])
        self.assertNotIn('best_day', facts)
        self.assertNotIn('best_day_revenue', facts)

    def test_growth_none_when_no_previous_week(self):
        sales = [
            FakeDoc('a1', {'shopId': 'shop1', 'totalAmount': 1000,
                           'saleDate': _days_ago_ts(0)}),
        ]
        db = FakeDB(collections={'sales': sales})

        facts = weekly_facts(db, 'shop1', {'name': 'Ma Boutique'})

        self.assertEqual(facts['revenue'], 1000.0)
        self.assertEqual(facts['prev_revenue'], 0.0)
        self.assertIsNone(facts['growth'])


class SendWeeklyRecapCommandTests(SimpleTestCase):
    def _build_db(self):
        shops = [FakeDoc('shop1', {'name': 'Ma Boutique', 'ownerId': 'owner1'})]
        sales = [
            FakeDoc('a1', {'shopId': 'shop1', 'totalAmount': 1000,
                           'saleDate': _days_ago_ts(0)}),
            FakeDoc('a2', {'shopId': 'shop1', 'totalAmount': 2000,
                           'saleDate': _days_ago_ts(1)}),
            FakeDoc('b1', {'shopId': 'shop1', 'totalAmount': 1500,
                           'saleDate': _days_ago_ts(8)}),
        ]
        return FakeDBWithShops(
            shops=shops,
            members_by_shop={},
            collections={'sales': sales},
            users={'owner1': FakeDoc('owner1', {'name': 'Awa Traore'})},
        )

    @patch('billing.management.commands.send_weekly_recap.notif_engine.compose_and_send')
    @patch('billing.management.commands.send_weekly_recap.fb.notif_settings')
    @patch('billing.management.commands.send_weekly_recap.fb.db')
    def test_dry_run_does_not_send(self, mock_db, mock_settings, mock_compose):
        mock_db.return_value = self._build_db()
        mock_settings.return_value = {'notif_weekly_recap': True}

        call_command('send_weekly_recap')  # pas de --commit

        mock_compose.assert_not_called()

    @patch('billing.management.commands.send_weekly_recap.notif_engine.compose_and_send')
    @patch('billing.management.commands.send_weekly_recap.fb.notif_settings')
    @patch('billing.management.commands.send_weekly_recap.fb.db')
    def test_commit_sends_with_expected_kind_and_push_data(
            self, mock_db, mock_settings, mock_compose):
        mock_db.return_value = self._build_db()
        mock_settings.return_value = {'notif_weekly_recap': True}
        mock_compose.return_value = 1

        call_command('send_weekly_recap', '--commit')

        mock_compose.assert_called_once()
        _, kwargs = mock_compose.call_args
        self.assertEqual(kwargs['uid'], 'owner1')
        self.assertEqual(kwargs['kind'], 'weekly')
        self.assertEqual(kwargs['push_data'],
                         {'type': 'weekly_recap', 'shopId': 'shop1'})
        self.assertEqual(kwargs['fallback_title'], 'Ton bilan de la semaine')
        body = kwargs['fallback_body']
        self.assertIn('vente(s)', body)
        self.assertIn('semaine dernière', body)
        self.assertEqual(kwargs['facts']['first_name'], 'Awa')

    @patch('billing.management.commands.send_weekly_recap.notif_engine.compose_and_send')
    @patch('billing.management.commands.send_weekly_recap.fb.notif_settings')
    @patch('billing.management.commands.send_weekly_recap.fb.db')
    def test_commit_skips_recipient_with_setting_disabled(
            self, mock_db, mock_settings, mock_compose):
        mock_db.return_value = self._build_db()
        mock_settings.return_value = {'notif_weekly_recap': False}

        call_command('send_weekly_recap', '--commit')

        mock_compose.assert_not_called()

    @patch('billing.management.commands.send_weekly_recap.notif_engine.compose_and_send')
    @patch('billing.management.commands.send_weekly_recap.fb.notif_settings')
    @patch('billing.management.commands.send_weekly_recap.fb.db')
    def test_commit_skips_shop_with_no_sales(
            self, mock_db, mock_settings, mock_compose):
        shops = [FakeDoc('shop1', {'name': 'Boutique calme', 'ownerId': 'owner1'})]
        db = FakeDBWithShops(
            shops=shops, members_by_shop={}, collections={'sales': []}, users={},
        )
        mock_db.return_value = db
        mock_settings.return_value = {'notif_weekly_recap': True}

        call_command('send_weekly_recap', '--commit')

        mock_compose.assert_not_called()
