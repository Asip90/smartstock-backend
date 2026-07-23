from django.urls import path

from . import views

urlpatterns = [
    path('', views.home, name='storefront_home'),
    path('produit/<str:product_slug>', views.product_detail, name='storefront_product'),
    path('sitemap.xml', views.sitemap, name='storefront_sitemap'),
    path('robots.txt', views.robots, name='storefront_robots'),
]
