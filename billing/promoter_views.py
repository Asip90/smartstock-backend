from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
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
