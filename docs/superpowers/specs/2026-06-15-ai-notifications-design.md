# Spec — Moteur de notifications IA + briefing du matin

Date : 2026-06-15
Dépôt : `smartstock-backend` (Django + Jazzmin + DRF + Firebase Admin)
Branche : `feat/ai-notifications`

## Objectif

Rendre les notifications push **vivantes, humaines, concises et non répétitives** (à la
TikTok : courtes mais pointues), en générant le texte via un LLM (Mistral **ou**
OpenRouter), **pilotable entièrement depuis la page superadmin Jazzmin sans toucher au
code** (choix du provider, du modèle, de la clé API, du ton). Ajouter un nouveau canal :
le **briefing du matin**.

Décisions produit validées :
- Portée : **moteur IA réutilisable + briefing du matin**, appliqué aussi au bilan du soir
  et aux alertes de stock existants.
- Anti-répétition : **historique des derniers messages + rotation d'angles**.
- Personnalisation : **FR, avec prénom + chiffres réels**.

## Contexte existant (à réutiliser, ne pas réinventer)

- `billing/firebase_service.py` : `db()`, `tokens_for_uid(uid)`, `notif_settings(uid)`,
  `send_push(tokens, title, body, data)`. Initialisation Firebase Admin déjà en place.
- `billing/management/commands/send_daily_summary.py` : calcule déjà ventes du jour
  (nb, CA, encaissé, crédit) et envoie un push **statique**.
- `billing/management/commands/send_stock_alerts.py` : calcule déjà les produits sous
  seuil critique et envoie un push **statique**.
- `billing/models.py` `AppConfig` : **patron de modèle singleton éditable dans Jazzmin** à
  imiter pour la config IA.
- `requests==2.32.3` disponible.
- Collections Firestore : `shops` (`ownerId`, `name`), `produits` (`shopId`, `quantity`,
  `nbreCritique`, `name`), `sales` (`shopId`, `totalAmount`, `amountPaid`, `saleDate`),
  sous-collection `shops/{id}/members` (`userId`), `users/{uid}/settings/notifications`,
  `fcm_tokens` (`userId`). Crédits clients : collection à confirmer à l'implémentation
  (recherche : `credits` / `customers`) ; si introuvable, le fait « clients à relancer »
  est simplement omis du briefing (dégradation propre).

## Architecture

Fine couche « rédacteur IA » branchée sur la plomberie FCM existante, avec **repli
automatique** sur les messages templatés actuels. 6 composants :

### 1. `AIConfig` (modèle singleton, Jazzmin) — la page superadmin
Champs :
- `enabled: bool` (interrupteur maître IA, défaut False)
- `provider: char` choix `mistral` | `openrouter` (défaut `mistral`)
- `model: char` (ex. `mistral-small-latest`, `meta-llama/llama-3.1-8b-instruct`)
- `api_key: char` (rendu en champ masqué dans l'admin)
- `temperature: float` (défaut 0.9), `max_tokens: int` (défaut 120)
- `persona: text` (voix/ton, éditable sans code ; valeur par défaut fournie)
- `ai_morning: bool`, `ai_evening: bool`, `ai_stock: bool` (canaux passant par l'IA, défaut True)
- `updated_at`
- Pattern singleton : `pk=1` forcé, helper `AIConfig.get_solo()`.

### 2. `NotificationLog` (modèle) — anti-répétition + audit
Champs : `uid: char(index)`, `kind: char` (`morning`/`evening`/`stock`), `title`, `body`,
`angle: char`, `ai_used: bool`, `created_at: datetime(index)`. `ordering = ['-created_at']`.
Admin Jazzmin **en lecture seule** (liste consultable par le superadmin).
Helper `recent_for(uid, kind, n)` → liste des derniers `body` + dernier `angle`.

### 3. `billing/ai_service.py` — le cerveau
`generate_message(*, kind, facts: dict, recent: list[str], angle: str, lang='fr') -> str | None`
- Lit `AIConfig.get_solo()`. Si `not enabled`, pas de clé, ou canal coupé → `None`.
- System prompt = `persona` + règles dures (≤ 2 phrases, FR, ton = `angle`, interdiction
  de réutiliser les formulations de `recent`, pas de listes/markdown, montants en FCFA).
  User prompt = `facts` sérialisés en texte compact.
- Bascule URL selon provider (les deux sont OpenAI-compatible `/chat/completions`) :
  - mistral → `https://api.mistral.ai/v1/chat/completions`
  - openrouter → `https://openrouter.ai/api/v1/chat/completions`
  - en-tête `Authorization: Bearer {api_key}`, timeout 15 s.
- **Tout échec** (réseau, 401, quota, plus de crédit, JSON inattendu) → `try/except` →
  `None`. Nettoyage léger de la sortie (strip, retrait des guillemets, clamp longueur).

### 4. Rotation d'angles
Constantes par `kind` (ex. `factuel`, `motivant`, `conseil`, `encouragement`,
`félicitation`). `pick_angle(kind, last_angle)` → un angle ≠ `last_angle`.

### 5. `billing/notif_facts.py` — les faits (séparés de la rédaction)
Fonctions pures lisant Firestore, renvoyant des dict de chiffres réels :
- `morning_facts(db, shop_id, shop_data)` : ventes d'hier (nb, CA), ruptures du jour
  (nb + exemples), clients à relancer (nb + total dû, si collection dispo), best-seller.
- `evening_facts(db, shop_id, shop_data)` : nb ventes, CA, encaissé, crédit (logique
  reprise de `send_daily_summary`).
- `stock_facts(db, shop_id, shop_data)` : nb produits sous seuil + exemples (logique
  reprise de `send_stock_alerts`).
Aucune rédaction ici.

### 6. `billing/notif_engine.py` — composer + envoyer
`compose_and_send(*, uid, kind, facts, fallback_title, fallback_body, push_data) -> int`
1. `recent, last_angle = NotificationLog.recent_for(uid, kind)`
2. `angle = pick_angle(kind, last_angle)`
3. `body = ai_service.generate_message(...) or fallback_body` ; `ai_used` selon le cas
4. `sent = firebase_service.send_push(tokens, fallback_title, body, push_data)`
5. `NotificationLog.objects.create(...)`
6. retourne `sent`.
**Une notif part toujours** (repli garanti).

### 7. Commandes cron
- **NOUVEAU** `send_morning_briefing` : parcourt les boutiques, `morning_facts`, destinataires
  = propriétaire + membres ayant `notif_morning_briefing` (défaut True), via le moteur,
  `data={'type':'morning_briefing','shopId':...}`. Cron 7h (Africa/Porto-Novo).
- **REFACTOR** `send_daily_summary` : conserve son calcul, passe le corps par le moteur
  (canal `evening`), repli = corps templaté actuel. Comportement identique si IA off.
- **REFACTOR** `send_stock_alerts` : idem (canal `stock`).
- `firebase_service.notif_settings()` : ajouter la clé `notif_morning_briefing` (défaut True).

### 8. Compagnon Flutter (`smart_stock`)
Ajouter dans la page de réglages de notifications l'interrupteur
`notif_morning_briefing` (écrit dans `users/{uid}/settings/notifications`), aligné sur les
interrupteurs existants (`notif_daily_summary`, `notif_critical_stock`).

## Repli / sécurité
IA coupée, pas de clé, erreur, ou plus de crédit → message templaté actuel. Rien ne casse.
`NotificationLog.ai_used=False` rend le repli visible dans Jazzmin.

## Personnalisation / langue
FR. Prénom récupéré depuis `users/{uid}` (`name`/`displayName`) sinon Firebase Auth
`display_name` ; absent → message sans prénom. Montants en FCFA, séparateur espace.

## Coût
1 à 3 appels IA / commerçant / jour sur modèle économique (mistral-small / llama-8b) +
`max_tokens` bas ≈ négligeable. Pas d'optimisation prématurée.

## Tests
- `ai_service` : `requests` mocké → succès, 401, timeout, plus de crédit → `None` au repli ;
  respect du provider/URL ; nettoyage de sortie.
- `notif_engine` : repli quand `generate_message` renvoie `None` ; écriture `NotificationLog` ;
  `pick_angle` ≠ dernier angle.
- `AIConfig.get_solo()` singleton ; `NotificationLog.recent_for`.
- Firebase et HTTP réseau toujours mockés (aucun appel réel en test).

## Hors périmètre
Relances de dette automatiques (canal futur, réutilisera le moteur), réconciliation Mobile
Money, briefing affiché en page d'accueil (ici on couvre le push). Provider autres que
Mistral/OpenRouter.
