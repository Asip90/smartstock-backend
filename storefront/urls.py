from django.urls import path

from . import views

urlpatterns = [
    path('', views.home, name='storefront_home'),
    path('produit/<str:product_slug>', views.product_detail, name='storefront_product'),
    path('panier', views.cart_view, name='storefront_cart'),
    path('panier/ajouter', views.add_to_cart_view, name='storefront_cart_add'),
    path('panier/modifier', views.update_cart_view, name='storefront_cart_update'),
    path('panier/retirer', views.remove_from_cart_view, name='storefront_cart_remove'),
    path('commande', views.checkout_view, name='storefront_checkout'),
    path('paiement/retour', views.payment_return_view, name='storefront_payment_return'),
    path('sitemap.xml', views.sitemap, name='storefront_sitemap'),
    path('robots.txt', views.robots, name='storefront_robots'),
]
