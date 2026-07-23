"""Endpoint authentifié (Bearer Firebase) appelé par l'app Flutter quand le
propriétaire clique « Activer ma boutique » ou « Régénérer avec l'IA »."""
import json

from django.http import HttpResponseBadRequest, JsonResponse
from django.views.decorators.csrf import csrf_exempt

from . import firebase_service as fb
from .storefront_ai_service import generate_storefront_content


def _auth(request):
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
def generate_storefront_content_view(request):
    if request.method != 'POST':
        return HttpResponseBadRequest('POST requis')

    uid, _ = _auth(request)
    if not uid:
        return JsonResponse({'error': 'unauthorized'}, status=401)

    data = _body(request)
    shop_name = (data.get('shopName') or '').strip()
    if not shop_name:
        return JsonResponse({'error': 'shopName_requis'}, status=400)

    result = generate_storefront_content(
        shop_name=shop_name,
        shop_description=data.get('shopDescription') or '',
        products=data.get('products') or [],
        location=data.get('location') or '',
    )
    if result is None:
        return JsonResponse({'error': 'generation_indisponible'}, status=503)
    return JsonResponse(result)
