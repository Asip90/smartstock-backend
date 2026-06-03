from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from .views import landing, legal, payment_ok, download_apk
from billing import promoter_views

urlpatterns = [
    path('', landing, name='landing'),
    path('admin/', admin.site.urls),
    path('api/', include('billing.urls')),

    # Téléchargement de l'APK Android (boutons « Télécharger l'app »).
    path('telecharger', download_apk, name='download_apk'),

    # Retour de paiement FedaPay (détecté par la WebView de l'app).
    path('paiement/ok', payment_ok, name='payment_ok'),

    # Pages legales
    path('confidentialite', legal, {'doc': 'confidentialite'}, name='privacy'),
    path('conditions', legal, {'doc': 'conditions'}, name='terms'),
    path('mentions-legales', legal, {'doc': 'mentions-legales'}, name='legal_notice'),

    # Espace promoteur
    path('promoteur/inscription', promoter_views.promoter_signup, name='promoter_signup'),
    path('promoteur/bienvenue', promoter_views.promoter_welcome, name='promoter_welcome'),
    path('promoteur/code', promoter_views.promoter_create_code, name='promoter_create_code'),
    path('promoteur/connexion', promoter_views.promoter_login, name='promoter_login'),
    path('promoteur/', promoter_views.promoter_dashboard, name='promoter_dashboard'),
    path('promoteur/retrait', promoter_views.promoter_withdraw, name='promoter_withdraw'),
    path('promoteur/deconnexion', promoter_views.promoter_logout, name='promoter_logout'),
]

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
