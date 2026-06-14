# Plan — Moteur de notifications IA + briefing du matin

Spec : `docs/superpowers/specs/2026-06-15-ai-notifications-design.md`
Dépôt : `smartstock-backend` (sauf Tâche 6 → `smart_stock`)
Branche backend : `feat/ai-notifications`

Exécution : subagent-driven (un sous-agent par tâche, séquentiel, puis revue conformité +
revue qualité). Tests réseau/Firebase **toujours mockés**.

---

## Tâche 1 — Modèles `AIConfig` + `NotificationLog` + admin Jazzmin

**Fichiers** : `billing/models.py`, `billing/admin.py`, migration.

**Étapes**
1. `AIConfig` (singleton) dans `billing/models.py` : champs `enabled` (défaut False),
   `provider` (choices mistral/openrouter, défaut mistral), `model` (char, défaut
   `mistral-small-latest`), `api_key` (char blank), `temperature` (float défaut 0.9),
   `max_tokens` (int défaut 120), `persona` (text, défaut = ton humain/concis/FR fourni),
   `ai_morning`/`ai_evening`/`ai_stock` (bool défaut True), `updated_at`.
   - `save()` force `pk=1` ; classmethod `get_solo()` (get_or_create pk=1).
   - `Meta.verbose_name = "Configuration IA"` (sing. = plur.).
2. `NotificationLog` : `uid` (char, db_index), `kind` (char), `title`, `body` (text),
   `angle` (char), `ai_used` (bool), `created_at` (auto_now_add, db_index).
   `Meta.ordering = ['-created_at']`. classmethod `recent_for(uid, kind, n=6) ->
   tuple[list[str], str|None]` (liste des `body`, dernier `angle`).
3. `billing/admin.py` : enregistrer `AIConfig` (api_key en `forms.PasswordInput`
   via un ModelAdmin form, ou widget masqué) ; `NotificationLog` en lecture seule
   (`has_add_permission`/`has_change_permission` False, `list_display`, `list_filter`
   sur kind/ai_used, `search_fields` uid).
4. `python manage.py makemigrations billing`.

**Vérif** : `python manage.py makemigrations --check --dry-run` (ne propose plus rien après
génération) et `python manage.py check`.

---

## Tâche 2 — `billing/ai_service.py` (client LLM + génération)

**Fichiers** : `billing/ai_service.py` (nouveau), `billing/tests_ai_service.py` (nouveau).
Dépend de Tâche 1 (`AIConfig`).

**Étapes**
1. Constantes URL provider. `_endpoint(provider)` renvoie l'URL.
2. `generate_message(*, kind, facts, recent, angle, lang='fr') -> str | None` :
   lit `AIConfig.get_solo()` ; garde-fous (enabled, clé, canal `ai_<kind>`) → `None` ;
   construit messages system+user ; POST via `requests` (timeout 15s, Bearer) ;
   parse `choices[0].message.content` ; nettoyage (strip, retire guillemets entourants,
   clamp ~200 char) ; `try/except Exception` global → `None`.
3. Tests (requests mocké, AIConfig en base de test) : succès renvoie texte nettoyé ;
   IA désactivée → None ; pas de clé → None ; canal coupé → None ; 401/timeout/JSON
   invalide → None ; provider mistral vs openrouter → bonne URL appelée.

**Vérif** : `python manage.py test billing.tests_ai_service`.

---

## Tâche 3 — `billing/notif_facts.py` (faits Firestore)

**Fichiers** : `billing/notif_facts.py` (nouveau), `billing/tests_notif_facts.py` (nouveau).
Dépend de `firebase_service` uniquement.

**Étapes**
1. `evening_facts(db, shop_id, shop_data)` : reprendre le calcul de `send_daily_summary`
   (nb ventes, CA, encaissé, crédit). Renvoyer dict + `shop_name`.
2. `stock_facts(db, shop_id, shop_data)` : reprendre le calcul de `send_stock_alerts`
   (produits sous `nbreCritique`/défaut 5 ; nb + exemples).
3. `morning_facts(db, shop_id, shop_data)` : ventes d'hier (nb, CA), ruptures du jour
   (réutilise la logique stock), clients à relancer (tenter collection `credits`/`customers` ;
   absente/erreur → champ omis), best-seller d'hier si calculable simplement.
4. Helper `first_name(db, uid)` : `users/{uid}` (`name`/`displayName`) sinon `''`.
5. Tests : `db` Firestore mocké (faux `.collection().where().stream()`), vérifier les
   agrégats sur des données fixtures ; dégradation si collection crédits absente.

**Vérif** : `python manage.py test billing.tests_notif_facts`.

---

## Tâche 4 — `billing/notif_engine.py` (compose + envoie) + angles

**Fichiers** : `billing/notif_engine.py` (nouveau), `billing/tests_notif_engine.py` (nouveau).
Dépend de Tâches 1, 2 et de `firebase_service`.

**Étapes**
1. `ANGLES: dict[str, list[str]]` par kind ; `pick_angle(kind, last_angle)` (≠ last).
2. `compose_and_send(*, uid, kind, facts, fallback_title, fallback_body, push_data) -> int` :
   `recent_for` → `pick_angle` → `ai_service.generate_message` (or fallback) →
   `firebase_service.tokens_for_uid` + `send_push` → `NotificationLog.create` → retour sent.
3. Tests : `ai_service` et `firebase_service` mockés. Repli quand generate → None
   (body = fallback, ai_used False) ; succès IA (ai_used True) ; `NotificationLog` écrit ;
   `pick_angle` jamais égal au dernier.

**Vérif** : `python manage.py test billing.tests_notif_engine`.

---

## Tâche 5 — Commandes cron (morning + refactors) + réglage

**Fichiers** : `billing/management/commands/send_morning_briefing.py` (nouveau),
`send_daily_summary.py` (refactor), `send_stock_alerts.py` (refactor),
`billing/firebase_service.py` (ajout clé réglage).
Dépend de Tâches 3 et 4.

**Étapes**
1. `firebase_service.notif_settings()` : ajouter `notif_morning_briefing` (défaut True).
2. `send_morning_briefing` : boucle boutiques → `morning_facts` → destinataires (owner +
   members) filtrés sur `notif_morning_briefing` → `compose_and_send(kind='morning', ...)`
   avec un `fallback_title`/`fallback_body` templatés. Skip si aucun fait notable.
3. Refactor `send_daily_summary` : garder calcul → construire le `fallback_body` actuel →
   `compose_and_send(kind='evening', ...)` au lieu du `send_push` direct. Filtre
   `notif_daily_summary` conservé.
4. Refactor `send_stock_alerts` : idem, `kind='stock'`, filtre `notif_critical_stock`
   conservé, `fallback_body` = corps actuel.
5. Docstrings cron mises à jour (7h pour morning, fuseau Africa/Porto-Novo).

**Vérif** : `python manage.py check` ; les commandes s'importent
(`python manage.py help send_morning_briefing`). Pas d'appel Firestore réel.

---

## Tâche 6 — Compagnon Flutter : interrupteur briefing du matin

**Dépôt** : `smart_stock`. **Fichier** : page de réglages de notifications
(chercher `notif_daily_summary` / `notif_critical_stock` dans `lib/pages/`).

**Étapes**
1. Trouver l'écran qui gère les interrupteurs de notifications et leur écriture dans
   `users/{uid}/settings/notifications`.
2. Ajouter un interrupteur « Briefing du matin » lié à `notif_morning_briefing`
   (défaut activé), même style/comportement que les autres.
3. Respecter les règles design (theme.dart, pas de couleur en dur, FR via i18n si utilisé).

**Vérif** : `flutter analyze` (pas de nouvelle erreur).

---

## Revue finale
Après les 6 tâches : revue de code globale, puis `finishing-a-development-branch`.
