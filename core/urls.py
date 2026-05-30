from django.contrib import admin
from django.urls import path, include
from django.http import JsonResponse


def health(_request):
    return JsonResponse({'status': 'ok', 'service': 'smartstock-billing'})


urlpatterns = [
    path('', health),
    path('admin/', admin.site.urls),
    path('api/', include('billing.urls')),
]
