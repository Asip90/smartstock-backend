from django.conf import settings
from django.http import Http404
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
