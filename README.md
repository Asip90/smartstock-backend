# SmartStock — Backend abonnements (Django)

Backend sécurisé pour l'abonnement Pro (FedaPay) et les codes promo/commissions.
Déployable gratuitement sur **Railway**. Détient la clé secrète FedaPay et écrit
l'entitlement d'abonnement dans Firestore (l'app Flutter le lit seulement).

## Démarrage local
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # puis remplir les variables
python manage.py makemigrations billing
python manage.py migrate
python manage.py createsuperuser   # pour l'admin /admin
python manage.py runserver
```

## Variables d'environnement (voir .env.example)
- `SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS`
- `DATABASE_URL` (Railway/Postgres ; vide = SQLite local)
- `FEDAPAY_SECRET_KEY`, `FEDAPAY_ENV` (sandbox|live), `FEDAPAY_WEBHOOK_SECRET`
- `FIREBASE_SERVICE_ACCOUNT_JSON` : le JSON du compte de service Firebase (inline)
- `PRICE_MONTHLY` (1900), `PRICE_YEARLY` (15000)

## Déploiement Railway
1. Pousser ce repo sur GitHub, créer un projet Railway depuis le repo.
2. Ajouter un plugin **Postgres** (Railway fournit `DATABASE_URL`).
3. Renseigner les variables d'env ci-dessus (dont `FIREBASE_SERVICE_ACCOUNT_JSON` et les clés FedaPay).
4. Railway lance le `Procfile` (migrate + gunicorn).
5. Configurer le **webhook FedaPay** vers `https://<app>.railway.app/api/webhook/fedapay`.

## API (auth : header `Authorization: Bearer <Firebase ID token>`)
- `POST /api/signup` `{promo_code?}` → démarre l'essai (3 mois si code valide, sinon 1).
- `POST /api/subscribe` `{plan: monthly|yearly}` → renvoie `checkout_url` (à ouvrir en WebView).
- `POST /api/webhook/fedapay` → (FedaPay) confirme le paiement, prolonge l'abonnement, crée la commission 25% (1re année).
- `POST /api/me` → état d'abonnement (debug ; l'app lit surtout Firestore).

## Modèle Firestore écrit par le backend
`subscriptions/{uid}` : `plan`, `status` (trialing|active|expired), `trialEnd`, `currentPeriodEnd`, `updatedAt`.
Règle Firestore : lecture par le propriétaire, **écriture interdite côté client** (seul ce backend écrit via firebase-admin).

## Notes / TODO
- Vérifier le format exact des réponses FedaPay (`billing/fedapay.py`) avec la doc/clés réelles
  (champs `id`, `token`, `url`, structure du webhook, header de signature).
- Renouvellement **manuel** (pas d'auto-débit) : l'app rappelle l'échéance et relance `/subscribe`.
- Versement des commissions : **manuel** depuis l'admin Django (action « Marquer comme versée »).
