"""Throttle anti-spam minimal, par session Django — pas de compte client
donc pas d'autre identifiant fiable côté serveur ; suffisant pour dissuader
un spam basique de faux `storeOrders` sans dépendance externe (cf. spec,
section Sécurité)."""
import time

_SESSION_PREFIX = 'ratelimit_'


def too_many_attempts(request, key: str, *, max_attempts: int = 5,
                       window_seconds: int = 600) -> bool:
    """Enregistre une tentative pour `key` et renvoie True si `max_attempts`
    a été atteint/dépassé dans la fenêtre `window_seconds`. Les tentatives
    hors fenêtre sont purgées à chaque appel (la session ne grossit jamais
    indéfiniment)."""
    session_key = f'{_SESSION_PREFIX}{key}'
    now = time.time()
    attempts = [t for t in request.session.get(session_key, []) if now - t < window_seconds]
    attempts.append(now)
    request.session[session_key] = attempts
    request.session.modified = True
    return len(attempts) > max_attempts
