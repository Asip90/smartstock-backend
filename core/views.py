from pathlib import Path

from django.conf import settings
from django.http import Http404, HttpResponse, FileResponse
from django.shortcuts import render

_SUPPORT = "Support : WhatsApp +229 01 90 63 77 30 — support@smartstock.app"
_UPDATED = "30 mai 2026"

# Documents legaux — contenu aligne sur l'application mobile.
LEGAL_DOCS = {
    'confidentialite': {
        'title': 'Politique de confidentialité',
        'intro': "SmartStock attache une grande importance à la protection de vos données. "
                 "Cette politique explique quelles données sont collectées, pourquoi, et comment elles sont protégées.",
        'sections': [
            ("1. Données collectées",
             "Nous collectons les informations de votre compte (nom, e-mail, photo de profil), "
             "les données de vos boutiques (nom, logo, coordonnées) et les données de gestion que "
             "vous saisissez : produits, catégories, ventes, réapprovisionnements et clients."),
            ("2. Utilisation des données",
             "Vos données servent uniquement au fonctionnement de l'application : afficher votre stock, "
             "enregistrer vos ventes, calculer vos statistiques et bénéfices, et synchroniser vos "
             "appareils. Nous ne vendons ni ne louons vos données à des tiers."),
            ("3. Stockage et sécurité",
             "Les données sont hébergées sur Google Firebase (Cloud Firestore) et les images sur Cloudinary. "
             "L'accès est restreint à votre compte. Les actions effectuées hors connexion sont "
             "conservées localement puis synchronisées de façon sécurisée au retour du réseau."),
            ("4. Conservation",
             "Vos données sont conservées tant que votre compte est actif. Vous pouvez demander leur "
             "suppression à tout moment en nous contactant."),
            ("5. Vos droits",
             "Vous disposez d'un droit d'accès, de rectification et de suppression de vos données. "
             "Pour exercer ces droits, contactez-nous. " + _SUPPORT),
        ],
    },
    'conditions': {
        'title': "Conditions d'utilisation",
        'intro': "En utilisant SmartStock, vous acceptez les présentes conditions. Veuillez les lire attentivement.",
        'sections': [
            ("1. Objet du service",
             "SmartStock est une application de gestion de stock et de ventes destinée aux commerçants. "
             "Elle vous permet de gérer vos produits, vos ventes, vos réapprovisionnements et vos statistiques."),
            ("2. Compte utilisateur",
             "Vous êtes responsable de la confidentialité de vos identifiants et de toutes les activités "
             "réalisées depuis votre compte. Fournissez des informations exactes lors de l'inscription."),
            ("3. Usage acceptable",
             "Vous vous engagez à utiliser l'application conformément à la loi et à ne pas tenter d'en "
             "perturber le fonctionnement ni d'accéder aux données d'autres utilisateurs."),
            ("4. Abonnement Pro",
             "L'abonnement Pro est facturé 1 900 F/mois ou 15 000 F/an via FedaPay. Le renouvellement est "
             "manuel : vous êtes notifié à l'échéance et choisissez de renouveler. À la fin d'une période payée "
             "sans renouvellement, le compte revient au plan gratuit."),
            ("5. Responsabilité",
             "SmartStock est un outil d'aide à la gestion. Vous restez seul responsable de l'exactitude "
             "des données saisies et des décisions commerciales prises sur cette base. Le service est "
             "fourni « en l'état », sans garantie de disponibilité permanente."),
            ("6. Modifications et résiliation",
             "Ces conditions peuvent évoluer ; les changements importants vous seront signalés. "
             "Vous pouvez cesser d'utiliser l'application à tout moment. " + _SUPPORT),
        ],
    },
    'mentions-legales': {
        'title': 'Mentions légales',
        'intro': "Informations relatives à l'éditeur et à l'hébergement de l'application SmartStock.",
        'sections': [
            ("Éditeur",
             "L'application SmartStock est éditée par son propriétaire. Pour toute question : " + _SUPPORT),
            ("Hébergement",
             "Les données et services sont hébergés par Google Firebase (Google LLC) et les médias par "
             "Cloudinary. Ces prestataires assurent la disponibilité et la sécurité de l'infrastructure."),
            ("Propriété intellectuelle",
             "La marque, le logo et le contenu de l'application sont protégés. Toute reproduction non "
             "autorisée est interdite."),
            ("Contact",
             "Pour toute réclamation ou demande d'information : " + _SUPPORT),
        ],
    },
}


def landing(request):
    return render(request, 'landing/landing.html', {
        'download_url': settings.APP_DOWNLOAD_URL,
        'price_monthly': settings.PRICE_MONTHLY,
        'price_yearly': settings.PRICE_YEARLY,
    })


def download_apk(request):
    """Sert l'APK Android (téléchargement depuis la landing page).
    Le fichier est versionné dans le repo sous downloads/smartstock.apk."""
    apk_path = Path(settings.BASE_DIR) / 'downloads' / 'smartstock.apk'
    if not apk_path.exists():
        raise Http404("APK indisponible")
    return FileResponse(
        open(apk_path, 'rb'),
        as_attachment=True,
        filename='SmartStock.apk',
        content_type='application/vnd.android.package-archive',
    )


def payment_ok(request):
    """Page de retour après paiement FedaPay. L'app mobile détecte l'URL
    « /paiement/ok » dans sa WebView pour la fermer automatiquement ; l'accès
    Pro est activé en arrière-plan par le webhook (Firestore subscriptions/{uid})."""
    html = """<!doctype html><html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Paiement reçu</title>
<style>body{font-family:system-ui,Segoe UI,Roboto,sans-serif;background:#F1F5F9;
color:#1E3A5F;display:flex;min-height:100vh;align-items:center;justify-content:center;margin:0}
.card{background:#fff;border:1px solid #E2E8F0;border-radius:20px;padding:32px;max-width:340px;
text-align:center}.check{width:72px;height:72px;border-radius:50%;background:#16A34A;color:#fff;
display:flex;align-items:center;justify-content:center;font-size:38px;margin:0 auto 16px}
h1{font-size:20px;margin:0 0 8px}p{color:#475569;font-size:14px;line-height:1.5}</style></head>
<body><div class="card"><div class="check">&#10003;</div>
<h1>Paiement reçu</h1><p>Votre abonnement SmartStock Pro est en cours d'activation.
Vous pouvez revenir à l'application.</p></div></body></html>"""
    return HttpResponse(html)


def legal(request, doc):
    data = LEGAL_DOCS.get(doc)
    if data is None:
        raise Http404("Document introuvable")
    return render(request, 'landing/legal.html', {
        'doc_title': data['title'],
        'doc_intro': data['intro'],
        'doc_sections': data['sections'],
        'doc_updated': _UPDATED,
        'download_url': settings.APP_DOWNLOAD_URL,
    })
