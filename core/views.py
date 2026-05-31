from django.conf import settings
from django.shortcuts import render


def landing(request):
    return render(request, 'landing/landing.html', {
        'download_url': settings.APP_DOWNLOAD_URL,
        'price_monthly': settings.PRICE_MONTHLY,
        'price_yearly': settings.PRICE_YEARLY,
    })
