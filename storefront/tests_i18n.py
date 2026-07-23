from django.test import TestCase

from storefront.i18n import t


class TranslationTests(TestCase):
    def test_fr_par_defaut_pour_langue_inconnue(self):
        self.assertEqual(t('shop_now', 'de'), t('shop_now', 'fr'))

    def test_en_renvoie_texte_different_du_fr(self):
        self.assertNotEqual(t('shop_now', 'fr'), t('shop_now', 'en'))

    def test_cle_inconnue_renvoie_la_cle_elle_meme(self):
        self.assertEqual(t('cle_qui_nexiste_pas', 'fr'), 'cle_qui_nexiste_pas')
