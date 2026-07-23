from django.urls import path
from . import views
from . import promoter_api
from . import storefront_ai_views

urlpatterns = [
    path('signup', views.signup),
    path('apply-promo', views.apply_promo),
    path('subscribe', views.subscribe),
    path('confirm', views.confirm),
    path('webhook/fedapay', views.webhook),
    path('me', views.me),
    path('crash', views.crash),
    path('notify-owner', views.notify_owner),
    path('promoter/me', promoter_api.promoter_me),
    path('promoter/code', promoter_api.promoter_create_code),
    path('promoter/dashboard', promoter_api.promoter_dashboard),
    path('promoter/withdraw', promoter_api.promoter_withdraw),
    path('shop/generate-storefront-content', storefront_ai_views.generate_storefront_content_view),
]
