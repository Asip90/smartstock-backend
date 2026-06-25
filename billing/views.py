import json
from datetime import timedelta

from django.conf import settings
from django.http import JsonResponse, HttpResponseBadRequest
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from . import firebase_service as fb
from . import fedapay
from .models import PromoCode, Referral, Transaction, Commission, CrashReport


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


def _discounted_amount(plan, ref):
    """Montant à payer pour ce plan compte tenu de la remise filleul restante.

    Offre « 3 premiers mois » à -50% :
    - mensuel : -50% tant qu'il reste des mois remisés ;
    - annuel : réduction unique = (mois restants) x (mensuel // 2), pour offrir
      la même valeur cadeau sans brader une demi-année.
    Retourne (montant, remise_appliquee).
    """
    base = settings.PRICE_MONTHLY if plan == 'monthly' else settings.PRICE_YEARLY
    left = ref.discount_months_left if ref else 0
    if not ref or left <= 0:
        return base, False
    if plan == 'monthly':
        return base // 2, True
    reduction = left * (settings.PRICE_MONTHLY // 2)
    return max(0, base - reduction), True


def _promo_state(uid):
    """État du code promo pour l'app (page d'abonnement) : éligibilité au champ,
    avantage en cours, et prix normaux/remisés des deux plans."""
    ref = Referral.objects.filter(referred_uid=uid).first()
    monthly_final, monthly_disc = _discounted_amount('monthly', ref)
    yearly_final, yearly_disc = _discounted_amount('yearly', ref)
    return {
        'referred': bool(ref),
        # Le champ « ajouter un code » n'apparaît que pour qui n'a pas encore de code.
        'can_apply_promo': not ref,
        'promo_code': ref.promo_code.code if ref else '',
        'influencer_name': ref.promo_code.influencer_name if ref else '',
        'discount_months_left': ref.discount_months_left if ref else 0,
        'discount_active': monthly_disc or yearly_disc,
        'prices': {
            'monthly': {'normal': settings.PRICE_MONTHLY, 'final': monthly_final,
                        'discounted': monthly_disc},
            'yearly': {'normal': settings.PRICE_YEARLY, 'final': yearly_final,
                       'discounted': yearly_disc},
        },
    }


@csrf_exempt
def signup(request):
    """Initialise l'essai. {promo_code?}. Essai = 30 jours ; le code ne l'allonge plus.

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

    trial_days = 30  # essai unique de 30 jours (1 mois), le code ne l'allonge plus
    if code:
        promo = PromoCode.objects.filter(code__iexact=code, active=True).first()
        if not promo:
            return JsonResponse({'error': 'code_promo_invalide'}, status=400)
        if _is_self_referral(promo, uid, email):
            return JsonResponse({'error': 'auto_parrainage_interdit'}, status=400)
        # 1 seul parrainage par filleul (referred_uid est unique en base).
        Referral.objects.create(
            promo_code=promo,
            referred_uid=uid,
            referred_email=email,
            first_year_end=timezone.now() + timedelta(days=365),
        )

    trial_end = timezone.now() + timedelta(days=trial_days)
    fb.set_entitlement(uid, plan='pro', status='trialing', trial_end=trial_end,
                       current_period_end=trial_end)
    return JsonResponse({'status': 'trialing', 'trial_days': trial_days})


@csrf_exempt
def apply_promo(request):
    """Attache un code promo à un compte qui n'en a pas encore (depuis la page
    d'abonnement). Ouvre droit à -50% sur les 3 premiers mois. {promo_code}.

    Un seul code par compte à vie : si un code est déjà lié, on refuse.
    """
    if request.method != 'POST':
        return HttpResponseBadRequest('POST requis')
    uid, email = _auth(request)
    if not uid:
        return JsonResponse({'error': 'unauthorized'}, status=401)

    if Referral.objects.filter(referred_uid=uid).exists():
        return JsonResponse({'error': 'code_promo_deja_utilise'}, status=409)

    code = (_body(request).get('promo_code') or '').strip()
    if not code:
        return JsonResponse({'error': 'code_promo_requis'}, status=400)
    promo = PromoCode.objects.filter(code__iexact=code, active=True).first()
    if not promo:
        return JsonResponse({'error': 'code_promo_invalide'}, status=400)
    if _is_self_referral(promo, uid, email):
        return JsonResponse({'error': 'auto_parrainage_interdit'}, status=400)

    Referral.objects.create(
        promo_code=promo,
        referred_uid=uid,
        referred_email=email,
        first_year_end=timezone.now() + timedelta(days=365),
    )
    return JsonResponse({'status': 'ok', 'promo': _promo_state(uid)})


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
    # Remise filleul : -50% sur les 3 premiers mois (cf. _discounted_amount).
    ref = Referral.objects.filter(referred_uid=uid).first()
    amount, discounted = _discounted_amount(plan, ref)

    tx = Transaction.objects.create(uid=uid, email=email, plan=plan, amount=amount,
                                    discounted=discounted)
    try:
        # Après paiement, FedaPay redirige vers cette page : l'app détecte l'URL
        # « /paiement/ok » dans la WebView pour la fermer automatiquement.
        callback_url = request.build_absolute_uri('/paiement/ok')
        checkout = fedapay.create_checkout(
            amount=amount,
            description=f'Abonnement Compa ({plan})',
            customer_email=email,
            callback_url=callback_url,
        )
    except Exception as e:
        tx.status = 'failed'
        tx.save()
        return JsonResponse({'error': f'fedapay: {e}'}, status=502)

    tx.fedapay_id = checkout['fedapay_id']
    tx.save()
    return JsonResponse({'checkout_url': checkout['url'], 'token': checkout['token'],
                         'transaction_id': tx.id, 'discounted': discounted})


def _is_self_referral(promo, uid, email):
    """Vrai si l'utilisateur (uid/email) est le propriétaire du code promo :
    on interdit l'auto-parrainage (toucher une commission sur son propre
    abonnement, et s'auto-octroyer la remise filleul)."""
    if promo.firebase_uid and promo.firebase_uid == uid:
        return True
    owner = promo.owner
    if owner and email and owner.email and owner.email.lower() == email.lower():
        return True
    return False


FEDAPAY_PAID_STATUSES = ('approved', 'paid', 'completed')


def _apply_paid_transaction(tx):
    """Confirme une transaction payée : prolonge l'abonnement, crée la commission
    et décompte la remise. Source de vérité unique appelée par le webhook,
    l'endpoint /api/confirm et la commande de réconciliation.

    Idempotente : ne fait rien (retourne False) si la transaction est déjà payée.
    """
    if tx.status == 'paid':
        return False
    tx.status = 'paid'
    tx.paid_at = timezone.now()
    tx.save(update_fields=['status', 'paid_at'])

    # Prolonge l'entitlement. On repart de maintenant (renouvellement manuel,
    # pas de chevauchement critique).
    days = 365 if tx.plan == 'yearly' else 30
    new_end = timezone.now() + timedelta(days=days)
    fb.set_entitlement(tx.uid, plan='pro', status='active', current_period_end=new_end)
    fb.mirror_pro_to_shops(tx.uid, new_end)

    # Commission influenceur : commission_pct % si le filleul est dans sa 1re année.
    # Pas de commission sur un auto-parrainage (le promoteur ne se paie pas lui-même).
    ref = Referral.objects.filter(referred_uid=tx.uid).first()
    if (ref and ref.is_within_first_year() and not hasattr(tx, 'commission')
            and not _is_self_referral(ref.promo_code, tx.uid, tx.email)):
        pct = ref.promo_code.commission_pct
        Commission.objects.create(
            referral=ref, transaction=tx, amount=tx.amount * pct // 100,
        )

    # Décompte des mois remisés restants (offre « 3 premiers mois »).
    if ref and tx.discounted and ref.discount_months_left > 0:
        ref.discount_months_left = (
            0 if tx.plan == 'yearly' else ref.discount_months_left - 1)
        ref.save(update_fields=['discount_months_left'])
    return True


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

    if status in FEDAPAY_PAID_STATUSES:
        _apply_paid_transaction(tx)

    return JsonResponse({'status': 'ok'})


@csrf_exempt
def confirm(request):
    """Confirmation de paiement initiée par l'app (filet de sécurité si le webhook
    FedaPay n'a pas été reçu). L'app appelle cet endpoint au retour de la WebView
    de paiement avec l'`transaction_id`. Le backend interroge FedaPay et, si la
    transaction est approuvée, applique la confirmation (idempotente)."""
    if request.method != 'POST':
        return HttpResponseBadRequest('POST requis')
    uid, _ = _auth(request)
    if not uid:
        return JsonResponse({'error': 'unauthorized'}, status=401)

    data = _body(request)
    tx = None
    tx_id = data.get('transaction_id')
    if tx_id:
        tx = Transaction.objects.filter(id=tx_id, uid=uid).first()
    if tx is None and data.get('fedapay_id'):
        tx = Transaction.objects.filter(
            fedapay_id=str(data['fedapay_id']), uid=uid).first()
    if tx is None:
        return JsonResponse({'error': 'transaction_introuvable'}, status=404)

    if tx.status != 'paid' and tx.fedapay_id:
        try:
            status = fedapay.get_transaction_status(tx.fedapay_id)
        except Exception:
            status = None
        if status in FEDAPAY_PAID_STATUSES:
            _apply_paid_transaction(tx)

    return JsonResponse({
        'status': tx.status,
        'entitlement': fb.get_entitlement(uid) or {'plan': 'free'},
    })


@csrf_exempt
def me(request):
    uid, _ = _auth(request)
    if not uid:
        return JsonResponse({'error': 'unauthorized'}, status=401)
    return JsonResponse({
        'entitlement': fb.get_entitlement(uid) or {'plan': 'free'},
        'promo': _promo_state(uid),
    })


@csrf_exempt
def notify_owner(request):
    """Un cogérant demande au propriétaire de renouveler l'abonnement Pro de la
    boutique. {shopId}. L'appelant doit être membre actif de la boutique."""
    if request.method != 'POST':
        return HttpResponseBadRequest('POST requis')
    uid, _ = _auth(request)
    if not uid:
        return JsonResponse({'error': 'unauthorized'}, status=401)

    shop_id = _body(request).get('shopId')
    if not shop_id:
        return JsonResponse({'error': 'shopId_requis'}, status=400)

    db = fb.db()
    member_doc = (db.collection('shops').document(shop_id)
                  .collection('members').document(uid).get())
    if not member_doc.exists:
        return JsonResponse({'error': 'forbidden'}, status=403)

    shop_doc = db.collection('shops').document(shop_id).get()
    if not shop_doc.exists:
        return JsonResponse({'error': 'boutique_introuvable'}, status=404)
    shop_data = shop_doc.to_dict() or {}
    owner_id = shop_data.get('ownerId')
    if not owner_id:
        return JsonResponse({'error': 'proprietaire_introuvable'}, status=404)
    name = shop_data.get('name', '')

    tokens = fb.tokens_for_uid(owner_id)
    sent = fb.send_push(
        tokens, "Renouvellement demandé",
        f"Un cogérant souhaite que vous renouveliez l'abonnement Pro de « {name} ».",
        data={'type': 'subscription', 'stage': 'owner_reminder'},
    )
    return JsonResponse({'ok': True, 'sent': sent})


@csrf_exempt
def crash(request):
    """Reçoit un rapport de crash de l'app et l'enregistre (visible dans Jazzmin).
    L'auth est facultative : un crash peut survenir hors session. On borne la
    taille des champs texte pour éviter des charges abusives."""
    if request.method != 'POST':
        return HttpResponseBadRequest('POST requis')
    uid, email = _auth(request)  # (None, None) si non authentifié
    data = _body(request)
    error = (data.get('error') or '').strip()
    if not error:
        return JsonResponse({'error': 'error_requis'}, status=400)
    CrashReport.objects.create(
        uid=uid or '',
        email=email or data.get('email', '') or '',
        platform=str(data.get('platform', ''))[:20],
        app_version=str(data.get('app_version', ''))[:40],
        build_number=str(data.get('build_number', ''))[:20],
        fatal=bool(data.get('fatal', False)),
        error=error[:5000],
        stack=(data.get('stack') or '')[:20000],
    )
    return JsonResponse({'status': 'ok'})
