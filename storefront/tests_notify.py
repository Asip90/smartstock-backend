from unittest.mock import patch

from django.test import TestCase

from storefront.notify import notify_new_order


class NotifyNewOrderTests(TestCase):
    @patch('storefront.notify.fb_service.record_notification')
    @patch('storefront.notify.fb_service.send_push')
    @patch('storefront.notify.fb_service.tokens_for_uid')
    @patch('storefront.notify.fb_read.get_shop_owner_uid')
    def test_envoie_le_push_et_enregistre_l_historique(
        self, mock_owner, mock_tokens, mock_send, mock_record,
    ):
        mock_owner.return_value = 'owner1'
        mock_tokens.return_value = ['tok1', 'tok2']

        notify_new_order('s1', 'Ma Boutique', 'order123', 5000)

        mock_tokens.assert_called_once_with('owner1')
        mock_send.assert_called_once()
        args, kwargs = mock_send.call_args
        self.assertEqual(args[0], ['tok1', 'tok2'])
        self.assertIn('Ma Boutique', args[1])
        mock_record.assert_called_once()
        record_kwargs = mock_record.call_args.kwargs
        self.assertEqual(record_kwargs['ntype'], 'new_online_order')

    @patch('storefront.notify.fb_service.record_notification')
    @patch('storefront.notify.fb_service.send_push')
    @patch('storefront.notify.fb_service.tokens_for_uid')
    @patch('storefront.notify.fb_read.get_shop_owner_uid')
    def test_ne_leve_pas_si_boutique_sans_proprietaire_resolu(
        self, mock_owner, mock_tokens, mock_send, mock_record,
    ):
        mock_owner.return_value = None

        notify_new_order('s1', 'Ma Boutique', 'order123', 5000)

        mock_tokens.assert_not_called()
        mock_send.assert_not_called()
        mock_record.assert_not_called()
