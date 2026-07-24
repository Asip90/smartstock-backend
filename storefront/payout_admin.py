"""Page d'admin dédiée aux demandes de retrait (solde boutique en ligne) —
volontairement séparée de l'admin Jazzmin (les demandes vivent en
Firestore, pas dans un modèle Django/Postgres). Réservée au staff Django
(`@staff_member_required`), jamais d'API publique pour approuver/rejeter."""
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib import messages
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from . import payouts


@staff_member_required
def payout_requests_view(request):
    pending = payouts.get_pending_payout_requests()
    return render(request, 'storefront/payout_requests.html', {'pending': pending})


@staff_member_required
@require_POST
def approve_payout_view(request, request_id: str):
    ok, message = payouts.approve_and_send(request_id)
    level = messages.SUCCESS if ok else messages.ERROR
    messages.add_message(request, level, message)
    return redirect('storefront_payout_requests')


@staff_member_required
@require_POST
def reject_payout_view(request, request_id: str):
    note = request.POST.get('note', '').strip()
    ok = payouts.reject(request_id, note)
    messages.add_message(
        request, messages.SUCCESS if ok else messages.ERROR,
        'Demande rejetée.' if ok else 'Échec du rejet (déjà traitée ?).',
    )
    return redirect('storefront_payout_requests')
