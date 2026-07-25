"""Webhook FedaPay DÉDIÉ à la boutique en ligne — route séparée de
`billing/views.py::webhook` (abonnements Pro) : un bug ici ne doit jamais
pouvoir casser la facturation. Se contente de faire transiter le statut de
la commande `pending -> paid` ; la vente (décrément de stock) reste créée
depuis l'app via `StoreOrderService.confirmOrder` (Dart), cf. design Phase 3
— pas de duplication de `SaleService` en Python."""
import json

from django.conf import settings
from django.http import HttpResponseBadRequest, JsonResponse
from django.views.decorators.csrf import csrf_exempt

from billing import fedapay

from . import orders

_PAID_STATUSES = ('approved', 'paid', 'completed')


@csrf_exempt
def webhook_view(request):
    if request.method != 'POST':
        return HttpResponseBadRequest('POST requis')

    signature = request.headers.get('X-FEDAPAY-SIGNATURE', '')
    if not fedapay.verify_webhook_signature(
        request.body, signature, secret=settings.FEDAPAY_STOREFRONT_WEBHOOK_SECRET,
    ):
        return JsonResponse({'error': 'signature_invalide'}, status=400)

    try:
        event = json.loads(request.body or b'{}')
    except ValueError:
        return JsonResponse({'error': 'payload_invalide'}, status=400)

    entity = event.get('entity') or event.get('data') or {}
    fedapay_id = str(entity.get('id', ''))
    status = (entity.get('status') or '').lower()

    if fedapay_id and status in _PAID_STATUSES:
        orders.mark_order_paid(fedapay_id)

    return JsonResponse({'status': 'ok'})
