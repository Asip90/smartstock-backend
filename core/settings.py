import os
from pathlib import Path

import dj_database_url
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-insecure-key')
DEBUG = os.environ.get('DEBUG', 'False').lower() == 'true'
ALLOWED_HOSTS = os.environ.get('ALLOWED_HOSTS', '*').split(',')
CSRF_TRUSTED_ORIGINS = [
    o for o in os.environ.get('CSRF_TRUSTED_ORIGINS', '').split(',') if o
]

INSTALLED_APPS = [
    'jazzmin',
    'corsheaders',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'billing',
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'core.urls'
WSGI_APPLICATION = 'core.wsgi.application'

# CORS : l'app Flutter Web appelle l'API depuis une autre origine (localhost en
# dev, domaine en prod). L'auth se fait par token Bearer Firebase (pas de cookie
# de session), donc autoriser toutes les origines est sans risque ici.
CORS_ALLOW_ALL_ORIGINS = True

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

# Base de données : DATABASE_URL (Railway/Postgres) sinon SQLite local.
_db_url = os.environ.get('DATABASE_URL')
if _db_url:
    DATABASES = {'default': dj_database_url.parse(_db_url, conn_max_age=600)}
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }

STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
# Stockage non-manifest : WhiteNoise compresse les statiques mais ne réécrit pas
# les références internes des JS, ce qui évite l'échec de `collectstatic` quand
# un fichier référence un sourcemap absent (ex. bootstrap.bundle.min.js.map de
# django-jazzmin). Le hash anti-cache n'est pas nécessaire pour l'admin.
STORAGES = {
    'staticfiles': {'BACKEND': 'whitenoise.storage.CompressedStaticFilesStorage'},
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
}

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [],
    'DEFAULT_PERMISSION_CLASSES': [],
}

# ── Config métier ───────────────────────────────────────────────────────────
FEDAPAY_SECRET_KEY = os.environ.get('FEDAPAY_SECRET_KEY', '')
FEDAPAY_ENV = os.environ.get('FEDAPAY_ENV', 'sandbox')
FEDAPAY_WEBHOOK_SECRET = os.environ.get('FEDAPAY_WEBHOOK_SECRET', '')
FIREBASE_SERVICE_ACCOUNT_JSON = os.environ.get('FIREBASE_SERVICE_ACCOUNT_JSON', '')

PRICE_MONTHLY = int(os.environ.get('PRICE_MONTHLY', '1900'))
PRICE_YEARLY = int(os.environ.get('PRICE_YEARLY', '15000'))

# Lien de téléchargement de l'app. Par défaut : APK servi par le backend
# (/telecharger). Surchargeable via l'env (ex. lien Play Store plus tard).
APP_DOWNLOAD_URL = os.environ.get('APP_DOWNLOAD_URL', '/telecharger')
STATICFILES_DIRS = [BASE_DIR / 'static']

# ── Admin (Jazzmin) ──────────────────────────────────────────────────────────
JAZZMIN_SETTINGS = {
    'site_title': 'SmartStock Admin',
    'site_header': 'SmartStock',
    'site_brand': 'SmartStock',
    'welcome_sign': 'Espace administration SmartStock',
    'copyright': 'SmartStock',
    'search_model': ['billing.PromoCode', 'billing.WithdrawalRequest'],
    'topmenu_links': [
        {'name': 'Site', 'url': '/', 'new_window': True},
        {'app': 'billing'},
    ],
    'icons': {
        'auth.User': 'fas fa-user',
        'auth.Group': 'fas fa-users',
        'billing.PromoCode': 'fas fa-ticket-alt',
        'billing.Referral': 'fas fa-user-plus',
        'billing.Transaction': 'fas fa-receipt',
        'billing.Commission': 'fas fa-coins',
        'billing.WithdrawalRequest': 'fas fa-money-bill-wave',
    },
    'order_with_respect_to': ['billing', 'auth'],
}
JAZZMIN_UI_TWEAKS = {
    'theme': 'flatly',
    'navbar': 'navbar-dark',
    'accent': 'accent-primary',
    'navbar_fixed': True,
    'sidebar_fixed': True,
}
