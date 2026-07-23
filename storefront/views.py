"""Vues publiques du site vitrine — servies via `storefront.urls`, dispatché
par `SubdomainStorefrontMiddleware` (jamais par `core/urls.py`)."""
from django.core.paginator import Paginator
from django.http import Http404, HttpResponse
from django.shortcuts import render

from . import firebase_read as fb_read
from .i18n import STRINGS, t

PAGE_SIZE = 24


def _lang(request) -> str:
    lang = request.GET.get('lang') or request.COOKIES.get('storefront_lang') or 'fr'
    return lang if lang in ('fr', 'en') else 'fr'


def _strings(lang: str) -> dict:
    """Dict précalculé { clé: texte traduit } pour tout `STRINGS` — Django ne
    permet pas d'appeler une fonction avec un argument depuis un template
    (`{{ t('home') }}` n'existe pas), donc on résout tout à l'avance et le
    template accède par attribut (`{{ t.home }}`, syntaxe Django standard sur
    un dict)."""
    return {key: t(key, lang) for key in STRINGS}


def _load_shop_or_none(request):
    slug = getattr(request, 'storefront_slug', None)
    return fb_read.get_shop_by_slug(slug) if slug else None


def _unavailable(request, lang, status=404):
    return render(request, 'storefront/unavailable.html', {
        'lang': lang, 't': _strings(lang),
    }, status=status)


def home(request):
    lang = _lang(request)
    shop = _load_shop_or_none(request)
    if shop is None:
        raise Http404('Boutique introuvable')
    if not shop['storefrontEnabled'] or not shop['isPro']:
        return _unavailable(request, lang)

    query = request.GET.get('q', '').strip()
    products = fb_read.list_public_products(shop['id'], search=query)
    categories = fb_read.list_categories(shop['id'])
    deals = [p for p in products if p['discountPrice']][:8]
    # Repli temporaire pour "populaires" en attendant les vraies statistiques
    # de vues (cf. plan, section "Écart supplémentaire").
    popular = sorted(products, key=lambda p: p['createdAt'] or 0, reverse=True)[:8]

    paginator = Paginator(products, PAGE_SIZE)
    page = paginator.get_page(request.GET.get('page') or 1)

    response = render(request, 'storefront/home.html', {
        'shop': shop, 'lang': lang, 't': _strings(lang),
        'categories': categories, 'deals': deals, 'popular': popular,
        'page': page, 'query': query,
    })
    response.set_cookie('storefront_lang', lang, max_age=60 * 60 * 24 * 365)
    return response


def product_detail(request, product_slug: str):
    lang = _lang(request)
    shop = _load_shop_or_none(request)
    if shop is None:
        raise Http404('Boutique introuvable')
    if not shop['storefrontEnabled'] or not shop['isPro']:
        return _unavailable(request, lang)

    product_id = product_slug.split('-', 1)[0]
    product = fb_read.get_public_product(shop['id'], product_id)
    if product is None:
        return render(request, 'storefront/product_not_found.html', {
            'shop': shop, 'lang': lang, 't': _strings(lang),
        }, status=404)

    return render(request, 'storefront/product_detail.html', {
        'shop': shop, 'product': product, 'lang': lang, 't': _strings(lang),
    })


def sitemap(request):
    shop = _load_shop_or_none(request)
    if shop is None or not shop['storefrontEnabled']:
        raise Http404('Boutique introuvable')

    base = f'https://{request.get_host()}'
    products = fb_read.list_public_products(shop['id'])
    urls = [base + '/'] + [f"{base}/produit/{p['url_slug']}" for p in products]
    body = '<?xml version="1.0" encoding="UTF-8"?>\n'
    body += '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    body += ''.join(f'<url><loc>{u}</loc></url>\n' for u in urls)
    body += '</urlset>'
    return HttpResponse(body, content_type='application/xml')


def robots(request):
    return HttpResponse(
        'User-agent: *\nAllow: /\nSitemap: /sitemap.xml\n',
        content_type='text/plain',
    )
