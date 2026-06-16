"""API JSON de l'espace promoteur pour l'app mobile.

Réutilise les modèles et la logique de solde de l'espace web (promoter_views),
mais l'authentification se fait via le Firebase ID token (header
Authorization: Bearer <idToken>), comme les autres endpoints mobiles (views.py).
"""
import re

from django.contrib.auth.models import User
from django.http import JsonResponse, HttpResponseBadRequest
from django.views.decorators.csrf import csrf_exempt

from .models import PromoCode, Referral, WithdrawalRequest
from .promoter_views import _balance
from .views import _auth, _body

CODE_RE = re.compile(r'^[A-Z0-9]{5,9}$')


def _resolve_promoter_user(email):
    """Compte Django associé au promoteur (clé = e-mail Firebase)."""
    return User.objects.get_or_create(username=email, defaults={'email': email})[0]


@csrf_exempt
def promoter_me(request):
    uid, email = _auth(request)
    if not uid:
        return JsonResponse({'error': 'unauthorized'}, status=401)
    user = _resolve_promoter_user(email)
    code = PromoCode.objects.filter(owner=user).first()
    if not code:
        return JsonResponse({'is_promoter': False, 'code': None, 'commission_pct': None})
    return JsonResponse({
        'is_promoter': True,
        'code': code.code,
        'commission_pct': code.commission_pct,
    })


@csrf_exempt
def promoter_create_code(request):
    if request.method != 'POST':
        return HttpResponseBadRequest('POST requis')
    uid, email = _auth(request)
    if not uid:
        return JsonResponse({'error': 'unauthorized'}, status=401)
    user = _resolve_promoter_user(email)

    code = (_body(request).get('code') or '').strip().upper()
    if not CODE_RE.match(code):
        return JsonResponse(
            {'error': 'Le code doit faire 5 à 9 caractères (lettres et chiffres uniquement).'},
            status=400)
    if PromoCode.objects.filter(code=code).exists():
        return JsonResponse({'error': 'Ce code est déjà pris.'}, status=400)
    if PromoCode.objects.filter(owner=user).exists():
        return JsonResponse({'error': 'Vous avez déjà un code promo.'}, status=409)

    PromoCode.objects.create(
        owner=user, code=code, influencer_name=email,
        commission_pct=25, active=True, firebase_uid=uid)
    return JsonResponse({'code': code})


@csrf_exempt
def promoter_dashboard(request):
    uid, email = _auth(request)
    if not uid:
        return JsonResponse({'error': 'unauthorized'}, status=401)
    user = _resolve_promoter_user(email)

    code = PromoCode.objects.filter(owner=user).first()
    if not code:
        return JsonResponse({'is_promoter': False})

    referrals_count = Referral.objects.filter(promo_code__owner=user).count()
    withdrawals = WithdrawalRequest.objects.filter(owner=user).order_by('-created_at')[:10]
    return JsonResponse({
        'code': code.code,
        'commission_pct': code.commission_pct,
        'balance': _balance(user),
        'referrals_count': referrals_count,
        'withdrawals': [{
            'amount': w.amount,
            'contact': w.contact,
            'status': w.status,
            'created_at': w.created_at.isoformat(),
        } for w in withdrawals],
    })


@csrf_exempt
def promoter_withdraw(request):
    if request.method != 'POST':
        return HttpResponseBadRequest('POST requis')
    uid, email = _auth(request)
    if not uid:
        return JsonResponse({'error': 'unauthorized'}, status=401)
    user = _resolve_promoter_user(email)

    data = _body(request)
    try:
        amount = int(data.get('amount', 0))
    except (TypeError, ValueError):
        amount = 0
    contact = (data.get('contact') or '').strip()

    bal = _balance(user)
    if not (0 < amount <= bal['available']):
        return JsonResponse(
            {'error': 'Montant invalide ou supérieur au solde disponible.'}, status=400)

    WithdrawalRequest.objects.create(
        owner=user, amount=amount, contact=contact, status='pending')
    return JsonResponse({'ok': True})
