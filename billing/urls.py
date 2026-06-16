from django.urls import path
from . import views
from . import promoter_api

urlpatterns = [
    path('signup', views.signup),
    path('subscribe', views.subscribe),
    path('webhook/fedapay', views.webhook),
    path('me', views.me),
    path('crash', views.crash),
    path('promoter/me', promoter_api.promoter_me),
    path('promoter/code', promoter_api.promoter_create_code),
    path('promoter/dashboard', promoter_api.promoter_dashboard),
    path('promoter/withdraw', promoter_api.promoter_withdraw),
]
