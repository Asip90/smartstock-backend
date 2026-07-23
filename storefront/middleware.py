"""Résout la boutique à partir du sous-domaine de la requête et bascule le
routing vers `storefront.urls` — `core/urls.py` n'est jamais modifié, le
domaine principal (landing/API) continue de résoudre normalement."""
from django.conf import settings


class SubdomainStorefrontMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        host = request.get_host().split(':')[0].lower()
        request.storefront_slug = None

        for base_domain in getattr(settings, 'STOREFRONT_BASE_DOMAINS', []):
            suffix = '.' + base_domain
            if host == base_domain or not host.endswith(suffix):
                continue
            label = host[: -len(suffix)]
            if label and label != 'www':
                request.storefront_slug = label
                request.urlconf = 'storefront.urls'
            break

        return self.get_response(request)
