from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from .views import landing
from billing import promoter_views

urlpatterns = [
    path('', landing, name='landing'),
    path('admin/', admin.site.urls),
    path('api/', include('billing.urls')),

    # Espace promoteur
    path('promoteur/connexion', promoter_views.promoter_login, name='promoter_login'),
    path('promoteur/', promoter_views.promoter_dashboard, name='promoter_dashboard'),
    path('promoteur/retrait', promoter_views.promoter_withdraw, name='promoter_withdraw'),
    path('promoteur/deconnexion', promoter_views.promoter_logout, name='promoter_logout'),
]

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
