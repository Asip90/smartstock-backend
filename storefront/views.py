"""Vues publiques du site vitrine — servies via `storefront.urls`, dispatché
par `SubdomainStorefrontMiddleware` (jamais par `core/urls.py`)."""
import datetime

from django.contrib import messages
from django.core.paginator import Paginator
from django.http import Http404, HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from . import cart as cart_mod
from . import firebase_read as fb_read
from . import notify
from . import ratelimit
from .i18n import STRINGS, t
from .orders import CartLineError, build_order_lines, create_order

PAGE_SIZE = 24
# Repère minimal pour trier par date sans mélanger types (None vs datetime) —
# cf. `home()` : les documents Firestore legacy peuvent ne pas avoir `createdAt`.
_EPOCH = datetime.datetime.min.replace(tzinfo=datetime.timezone.utc)


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


def _unavailable(request, lang, shop=None, status=404):
    return render(request, 'storefront/unavailable.html', {
        'lang': lang, 'shop': shop, 't': _strings(lang),
    }, status=status)


def home(request):
    lang = _lang(request)
    shop = _load_shop_or_none(request)
    if shop is None:
        raise Http404('Boutique introuvable')
    if not shop['storefrontEnabled'] or not shop['isPro']:
        return _unavailable(request, lang, shop=shop)

    query = request.GET.get('q', '').strip()
    products = fb_read.list_public_products(shop['id'], search=query)
    categories = fb_read.list_categories(shop['id'])
    deals = [p for p in products if p['discountPrice']][:8]
    # Repli temporaire pour "populaires" en attendant les vraies statistiques
    # de vues (cf. plan, section "Écart supplémentaire").
    popular = sorted(products, key=lambda p: p['createdAt'] or _EPOCH, reverse=True)[:8]

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
        return _unavailable(request, lang, shop=shop)

    product_id = product_slug.split('-', 1)[0]
    product = fb_read.get_public_product(shop['id'], product_id)
    if product is None:
        return render(request, 'storefront/product_not_found.html', {
            'shop': shop, 'lang': lang, 't': _strings(lang),
        }, status=404)

    return render(request, 'storefront/product_detail.html', {
        'shop': shop, 'product': product, 'lang': lang, 't': _strings(lang),
    })


def _redirect_back(request):
    """Retour à la page d'origine (repli accueil) — préserve la navigation
    du visiteur après une action panier, jamais une page blanche."""
    return redirect(request.META.get('HTTP_REFERER') or 'storefront_home')


@require_POST
def add_to_cart_view(request):
    shop = _load_shop_or_none(request)
    if shop is None:
        raise Http404('Boutique introuvable')
    lang = _lang(request)
    product_id = request.POST.get('product_id', '')
    try:
        qty = max(1, int(request.POST.get('qty', 1)))
    except ValueError:
        qty = 1
    cart_mod.add_to_cart(request, product_id, qty)
    messages.success(request, t('added_to_cart', lang))
    return _redirect_back(request)


@require_POST
def update_cart_view(request):
    shop = _load_shop_or_none(request)
    if shop is None:
        raise Http404('Boutique introuvable')
    product_id = request.POST.get('product_id', '')
    try:
        qty = int(request.POST.get('qty', 0))
    except ValueError:
        qty = 0
    cart_mod.set_quantity(request, product_id, qty)
    return redirect('storefront_cart')


@require_POST
def remove_from_cart_view(request):
    shop = _load_shop_or_none(request)
    if shop is None:
        raise Http404('Boutique introuvable')
    cart_mod.remove_from_cart(request, request.POST.get('product_id', ''))
    return redirect('storefront_cart')


def cart_view(request):
    lang = _lang(request)
    shop = _load_shop_or_none(request)
    if shop is None:
        raise Http404('Boutique introuvable')
    cart = cart_mod.get_cart(request)
    products = fb_read.get_public_products_by_ids(shop['id'], list(cart.keys()))
    lines = []
    for product_id, qty in cart.items():
        product = products.get(product_id)
        if product is None:
            continue  # produit devenu indisponible : simplement absent de l'affichage
        lines.append({'product': product, 'qty': qty, 'subtotal': product['price'] * qty})
    total = sum(line['subtotal'] for line in lines)
    return render(request, 'storefront/cart.html', {
        'shop': shop, 'lang': lang, 't': _strings(lang),
        'lines': lines, 'total': total,
    })


def checkout_view(request):
    lang = _lang(request)
    shop = _load_shop_or_none(request)
    if shop is None:
        raise Http404('Boutique introuvable')
    if not shop.get('allowCartOrder'):
        # La boutique existe et est bien en ligne (contrairement au cas
        # 404/shop introuvable) — seul le mode panier est désactivé, donc
        # 200 : c'est une réponse valide, pas une erreur.
        return _unavailable(request, lang, shop=shop, status=200)

    cart = cart_mod.get_cart(request)
    if not cart:
        return redirect('storefront_cart')

    if request.method == 'POST':
        if ratelimit.too_many_attempts(request, 'checkout'):
            messages.error(request, t('too_many_attempts', lang))
            return redirect('storefront_checkout')

        try:
            lines = build_order_lines(shop['id'], cart)
        except CartLineError as err:
            if err.reason == 'unavailable':
                cart_mod.remove_from_cart(request, err.product_id)
                messages.error(request, t('stock_error_unavailable', lang).format(name=err.product_name))
            else:
                cart_mod.set_quantity(request, err.product_id, err.available or 0)
                messages.error(
                    request,
                    t('stock_error_insufficient', lang).format(
                        name=err.product_name, available=err.available),
                )
            return redirect('storefront_cart')

        order_id = create_order(
            shop['id'],
            customer_name=request.POST.get('customer_name', '').strip(),
            customer_phone=request.POST.get('customer_phone', '').strip(),
            customer_address=request.POST.get('customer_address', '').strip(),
            lines=lines,
        )
        total = sum(line['price'] * line['qty'] for line in lines)
        notify.notify_new_order(shop['id'], shop['name'], order_id, total)
        cart_mod.clear_cart(request)
        return render(request, 'storefront/order_confirmation.html', {
            'shop': shop, 'lang': lang, 't': _strings(lang), 'order_id': order_id,
        })

    products = fb_read.get_public_products_by_ids(shop['id'], list(cart.keys()))
    lines = [
        {'product': products[pid], 'qty': qty, 'subtotal': products[pid]['price'] * qty}
        for pid, qty in cart.items() if pid in products
    ]
    total = sum(line['subtotal'] for line in lines)
    return render(request, 'storefront/checkout.html', {
        'shop': shop, 'lang': lang, 't': _strings(lang), 'lines': lines, 'total': total,
    })


def sitemap(request):
    shop = _load_shop_or_none(request)
    if shop is None or not shop['storefrontEnabled'] or not shop['isPro']:
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
