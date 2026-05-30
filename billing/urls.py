from django.urls import path
from . import views

urlpatterns = [
    path('signup', views.signup),
    path('subscribe', views.subscribe),
    path('webhook/fedapay', views.webhook),
    path('me', views.me),
]
