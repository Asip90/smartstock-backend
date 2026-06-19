# Déploiement — tâches planifiées (FCM) & FedaPay

Le plan Firebase **gratuit (Spark)** n'autorise pas les Cloud Functions. Les tâches
périodiques sont donc des **commandes Django** lancées par **cron** sur le VPS.

## 1. Crons FCM

| Commande | Rôle | Horaire conseillé |
|---|---|---|
| `send_stock_alerts` | Alerte stock critique (par boutique) | 07:00 |
| `expire_subscriptions` | Bascule `status→expired` + rappels J-3/J-1/J0 | 09:00 |
| `send_daily_summary` | Bilan des ventes du jour | 20:30 |

Installation :

```bash
cd /chemin/vers/smartstock-backend
chmod +x deploy/run_cron.sh
# Adapter le chemin absolu dans deploy/crontab.example, puis :
crontab deploy/crontab.example
crontab -l          # vérifier
```

Les commandes lisent les préférences de chaque utilisateur dans
`users/{uid}/settings/notifications` (toggles de la page Notifications de l'app).
Les **rappels d'abonnement** sont transactionnels : ils sont envoyés quels que
soient ces toggles.

Test manuel (sans attendre l'heure du cron) :

```bash
.venv/bin/python manage.py send_stock_alerts
.venv/bin/python manage.py expire_subscriptions
.venv/bin/python manage.py send_daily_summary
```

> `notif_new_sale` (toggle « nouvelle vente ») n'a **pas** d'émetteur : une notif
> par vente est événementielle et nécessiterait une Cloud Function (ou la clé
> serveur FCM dans l'app, à proscrire). Laissé dormant volontairement.

## 2. FedaPay — actions console (non automatisables)

Côté code, tout est prêt (`/api/subscribe`, `/api/webhook/fedapay`, vérification de
signature). Il reste à configurer, **dans le dashboard FedaPay** et sur le VPS :

1. **Webhook** : pointer vers `https://smartstock.nouyon.site/api/webhook/fedapay`
   (événement `transaction.approved` / paiement réussi).
2. **Variables d'environnement** (`.env` du projet sur le VPS) :
   - `FEDAPAY_SECRET_KEY` — clé secrète **live** (`sk_live_…`).
   - `FEDAPAY_ENV=live`.
   - `FEDAPAY_WEBHOOK_SECRET` — secret de signature du webhook.
   - `FIREBASE_SERVICE_ACCOUNT_JSON` — JSON du compte de service (une ligne) ou chemin.
   - `PRICE_MONTHLY`, `PRICE_YEARLY` (FCFA) si différents des valeurs par défaut.
3. Redémarrer le service web après modification du `.env`.
