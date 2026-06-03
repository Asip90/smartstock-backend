import re

from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db.models import Sum
from django.shortcuts import render, redirect
from django.utils import timezone

from .models import PromoCode, Commission, WithdrawalRequest


def _balance(user):
    """Calcule le solde du promoteur (commissions - retraits non rejetés)."""
    earned = Commission.objects.filter(
        referral__promo_code__owner=user).aggregate(s=Sum('amount'))['s'] or 0
    paid = WithdrawalRequest.objects.filter(
        owner=user, status='paid').aggregate(s=Sum('amount'))['s'] or 0
    pending = WithdrawalRequest.objects.filter(
        owner=user, status='pending').aggregate(s=Sum('amount'))['s'] or 0
    available = earned - paid - pending
    return {
        'earned': earned,
        'paid': paid,
        'pending': pending,
        'available': available if available > 0 else 0,
    }


def promoter_signup(request):
    """Auto-inscription d'un promoteur : crée le compte puis redirige vers
    l'écran de bienvenue (où il créera son code promo)."""
    if request.user.is_authenticated:
        return redirect('promoter_dashboard')
    error = None
    data = {}
    if request.method == 'POST':
        data = request.POST
        full_name = data.get('full_name', '').strip()
        email = data.get('email', '').strip().lower()
        password = data.get('password', '')
        password2 = data.get('password2', '')
        if not (full_name and email and password):
            error = 'Tous les champs sont requis.'
        elif password != password2:
            error = 'Les mots de passe ne correspondent pas.'
        elif len(password) < 6:
            error = 'Mot de passe trop court (6 caractères minimum).'
        elif User.objects.filter(username=email).exists():
            error = 'Un compte existe déjà avec cet e-mail.'
        else:
            user = User.objects.create_user(username=email, email=email, password=password)
            parts = full_name.split(' ', 1)
            user.first_name = parts[0]
            user.last_name = parts[1] if len(parts) > 1 else ''
            user.save()
            login(request, user)
            return redirect('promoter_welcome')
    return render(request, 'promoter/signup.html', {'error': error, 'data': data})


@login_required(login_url='promoter_login')
def promoter_welcome(request):
    """Écran de bienvenue animé, focalisé sur « Créer mon code promo »."""
    if PromoCode.objects.filter(owner=request.user).exists():
        return redirect('promoter_dashboard')
    return render(request, 'promoter/welcome.html')


@login_required(login_url='promoter_login')
def promoter_create_code(request):
    """Création du code promo choisi par le promoteur (5–9 caractères,
    alphanumérique), avec contrôle de disponibilité."""
    if PromoCode.objects.filter(owner=request.user).exists():
        return redirect('promoter_dashboard')
    error = None
    if request.method == 'POST':
        code = request.POST.get('code', '').strip().upper()
        if not re.fullmatch(r'[A-Z0-9]{5,9}', code):
            error = 'Le code doit faire 5 à 9 caractères (lettres et chiffres uniquement).'
        elif PromoCode.objects.filter(code=code).exists():
            error = f'Le code « {code} » est déjà pris. Choisis-en un autre.'
        else:
            PromoCode.objects.create(
                owner=request.user, code=code,
                influencer_name=request.user.get_full_name() or request.user.username,
                commission_pct=25, active=True)
            return render(request, 'promoter/code_created.html', {'code': code})
    return render(request, 'promoter/create_code.html', {'error': error})


def promoter_login(request):
    if request.user.is_authenticated:
        return redirect('promoter_dashboard')
    error = None
    if request.method == 'POST':
        user = authenticate(
            request,
            username=request.POST.get('username', '').strip(),
            password=request.POST.get('password', ''),
        )
        if user is not None:
            login(request, user)
            return redirect('promoter_dashboard')
        error = "Identifiants incorrects."
    return render(request, 'promoter/login.html', {'error': error})


@login_required(login_url='promoter_login')
def promoter_dashboard(request):
    user = request.user
    codes = PromoCode.objects.filter(owner=user, active=True)
    commissions = (Commission.objects
                   .filter(referral__promo_code__owner=user)
                   .select_related('transaction', 'referral')
                   .order_by('-created_at')[:20])
    withdrawals = WithdrawalRequest.objects.filter(owner=user).order_by('-created_at')[:10]
    return render(request, 'promoter/dashboard.html', {
        'codes': codes,
        'balance': _balance(user),
        'commissions': commissions,
        'withdrawals': withdrawals,
    })


@login_required(login_url='promoter_login')
def promoter_withdraw(request):
    if request.method != 'POST':
        return redirect('promoter_dashboard')
    user = request.user
    bal = _balance(user)
    try:
        amount = int(request.POST.get('amount', '0'))
    except ValueError:
        amount = 0
    contact = request.POST.get('contact', '').strip()

    if amount <= 0 or amount > bal['available']:
        return render(request, 'promoter/dashboard.html', {
            'codes': PromoCode.objects.filter(owner=user, active=True),
            'balance': bal,
            'commissions': Commission.objects.filter(
                referral__promo_code__owner=user).order_by('-created_at')[:20],
            'withdrawals': WithdrawalRequest.objects.filter(owner=user).order_by('-created_at')[:10],
            'error': 'Montant invalide ou supérieur au solde disponible.',
        })

    WithdrawalRequest.objects.create(owner=user, amount=amount, contact=contact)
    return redirect('promoter_dashboard')


def promoter_logout(request):
    logout(request)
    return redirect('promoter_login')
