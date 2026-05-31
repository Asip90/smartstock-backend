import json
from datetime import timedelta

from django.conf import settings
from django.http import JsonResponse, HttpResponseBadRequest
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from . import firebase_service as fb
from . import fedapay
from .models import PromoCode, Referral, Transaction, Commission


def _auth(request):
    """Retourne (uid, email) depuis le header Authorization: Bearer <idToken>."""
    header = request.headers.get('Authorization', '')
    if not header.startswith('Bearer '):
        return None, None
    try:
        return fb.verify_token(header.split(' ', 1)[1])
    except Exception:
        return None, None


def _body(request):
    try:
        return json.loads(request.body or b'{}')
    except Exception:
        return {}


@csrf_exempt
def signup(request):
    """Initialise l'essai. {promo_code?}. Essai = 3 mois si code valide, sinon 1 mois.

    Un utilisateur ne peut bénéficier de l'essai et d'un code promo qu'UNE SEULE
    FOIS à vie : tout appel ultérieur est rejeté (évite qu'on régénère un code à
    chaque fois pour ré-obtenir des mois gratuits).
    """
    if request.method != 'POST':
        return HttpResponseBadRequest('POST requis')
    uid, email = _auth(request)
    if not uid:
        return JsonResponse({'error': 'unauthorized'}, status=401)

    data = _body(request)
    code = (data.get('promo_code') or '').strip()

    # Un code promo déjà utilisé par ce compte ne peut pas l'être à nouveau.
    if Referral.objects.filter(referred_uid=uid).exists():
        return JsonResponse({'error': 'code_promo_deja_utilise'}, status=409)

    # Essai déjà initialisé (avec ou sans code) -> pas de ré-initialisation.
    existing = fb.get_entitlement(uid)
    if existing:
        if code:
            return JsonResponse({'error': 'essai_deja_utilise'}, status=409)
        return JsonResponse({'status': existing.get('status', 'free'), 'already': True})

    trial_months = 1
    if code:
        promo = PromoCode.objects.filter(code__iexact=code, active=True).first()
        if not promo:
            return JsonResponse({'error': 'code_promo_invalide'}, status=400)
        trial_months = promo.trial_months
        # 1 seul parrainage par filleul (referred_uid est unique en base).
        Referral.objects.create(
            promo_code=promo,
            referred_uid=uid,
            referred_email=email,
            first_year_end=timezone.now() + timedelta(days=365),
        )

    trial_end = timezone.now() + timedelta(days=30 * trial_months)
    fb.set_entitlement(uid, plan='pro', status='trialing', trial_end=trial_end,
                       current_period_end=trial_end)
    return JsonResponse({'status': 'trialing', 'trial_months': trial_months})


@csrf_exempt
def subscribe(request):
    """Crée une transaction FedaPay et renvoie l'URL de checkout. {plan: monthly|yearly}."""
    if request.method != 'POST':
        return HttpResponseBadRequest('POST requis')
    uid, email = _auth(request)
    if not uid:
        return JsonResponse({'error': 'unauthorized'}, status=401)

    plan = _body(request).get('plan', 'monthly')
    if plan not in ('monthly', 'yearly'):
        return JsonResponse({'error': 'plan_invalide'}, status=400)
    amount = settings.PRICE_MONTHLY if plan == 'monthly' else settings.PRICE_YEARLY

    tx = Transaction.objects.create(uid=uid, email=email, plan=plan, amount=amount)
    try:
        checkout = fedapay.create_checkout(
            amount=amount,
            description=f'Abonnement SmartStock ({plan})',
            customer_email=email,
        )
    except Exception as e:
        tx.status = 'failed'
        tx.save()
        return JsonResponse({'error': f'fedapay: {e}'}, status=502)

    tx.fedapay_id = checkout['fedapay_id']
    tx.save()
    return JsonResponse({'checkout_url': checkout['url'], 'token': checkout['token'],
                         'transaction_id': tx.id})


@csrf_exempt
def webhook(request):
    """Webhook FedaPay : confirme le paiement, prolonge l'abonnement, crée la commission."""
    if request.method != 'POST':
        return HttpResponseBadRequest('POST requis')
    signature = request.headers.get('X-FEDAPAY-SIGNATURE', '')
    if not fedapay.verify_webhook_signature(request.body, signature):
        return JsonResponse({'error': 'signature_invalide'}, status=400)

    event = _body(request)
    entity = (event.get('entity') or event.get('data') or {})
    fedapay_id = str(entity.get('id', ''))
    status = (entity.get('status') or '').lower()

    tx = Transaction.objects.filter(fedapay_id=fedapay_id).first()
    if not tx:
        return JsonResponse({'status': 'ignored'})

    if status in ('approved', 'paid', 'completed') and tx.status != 'paid':
        tx.status = 'paid'
        tx.paid_at = timezone.now()
        tx.save()

        # Prolonge l'entitlement.
        days = 365 if tx.plan == 'yearly' else 30
        current = fb.get_entitlement(tx.uid) or {}
        base = timezone.now()
        # NB : current['currentPeriodEnd'] est un Timestamp Firestore ; on repart de
        # maintenant pour rester simple (renouvellement manuel, pas de chevauchement critique).
        new_end = base + timedelta(days=days)
        fb.set_entitlement(tx.uid, plan='pro', status='active', current_period_end=new_end)

        # Commission influenceur : 25% si le filleul est dans sa 1re année.
        ref = Referral.objects.filter(referred_uid=tx.uid).first()
        if ref and ref.is_within_first_year() and not hasattr(tx, 'commission'):
            pct = ref.promo_code.commission_pct
            Commission.objects.create(
                referral=ref, transaction=tx, amount=tx.amount * pct // 100,
            )

    return JsonResponse({'status': 'ok'})


@csrf_exempt
def me(request):
    uid, _ = _auth(request)
    if not uid:
        return JsonResponse({'error': 'unauthorized'}, status=401)
    return JsonResponse({'entitlement': fb.get_entitlement(uid) or {'plan': 'free'}})
