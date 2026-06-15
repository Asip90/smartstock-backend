"""Client IA générique (provider-agnostic) pour le moteur de notifications.

Transforme des faits calculés (chiffres du jour, alertes de stock, etc.) en
UNE phrase courte, naturelle et non répétitive en français. Ne lève jamais
d'exception : en cas de souci (config absente, réseau, réponse invalide…),
``generate_message`` renvoie ``None`` et l'appelant doit utiliser un message
templaté de repli.
"""
import re

import requests

from .models import AIConfig

# Caractères considérés comme des guillemets « englobants » à retirer.
_QUOTE_PAIRS = [
    ('"', '"'),
    ("'", "'"),
    ('«', '»'),
    ('“', '”'),
]

_MAX_LEN = 200


def _facts_to_text(facts: dict) -> str:
    """Sérialise un dict de faits en lignes ``clé: valeur`` compactes."""
    return '\n'.join(f'{key}: {value}' for key, value in facts.items())


def _endpoint(provider: str) -> str | None:
    """Renvoie l'URL de l'API chat du provider, ou ``None`` si inconnu."""
    if provider == 'mistral':
        return 'https://api.mistral.ai/v1/chat/completions'
    if provider == 'openrouter':
        return 'https://openrouter.ai/api/v1/chat/completions'
    return None


def _clean(text: str) -> str:
    """Nettoie le texte renvoyé par le modèle : espaces, guillemets, taille."""
    cleaned = text.strip()

    for left, right in _QUOTE_PAIRS:
        if len(cleaned) >= 2 and cleaned.startswith(left) and cleaned.endswith(right):
            cleaned = cleaned[1:-1].strip()
            break

    # Collapse des retours à la ligne / espaces multiples en un seul espace.
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()

    if len(cleaned) > _MAX_LEN:
        truncated = cleaned[:_MAX_LEN]
        last_space = truncated.rfind(' ')
        if last_space > 0:
            truncated = truncated[:last_space]
        cleaned = truncated.rstrip('.,;: ') + '…'

    return cleaned


def generate_message(*, kind: str, facts: dict, recent: list[str], angle: str, lang: str = 'fr') -> str | None:
    """Génère une notification courte et naturelle à partir de ``facts``.

    Renvoie ``None`` si l'IA est désactivée, mal configurée, ou si la requête
    échoue pour quelque raison que ce soit (l'appelant doit alors utiliser un
    message templaté de repli).
    """
    cfg = AIConfig.get_solo()

    if not cfg.enabled:
        return None
    if not cfg.api_key:
        return None
    if not getattr(cfg, f'ai_{kind}', True):
        return None

    rules = (
        "Réponds en français. Une à deux phrases maximum. "
        f"Ton/angle de la notification : {angle}. "
        "Intègre les vrais chiffres fournis dans les faits. "
        "Les montants sont exprimés en FCFA avec un espace comme séparateur "
        "de milliers. N'utilise ni markdown, ni listes à puces, ni guillemets "
        "autour de la réponse."
    )
    if recent:
        rules += (
            " Ne réutilise aucune des formulations précédentes suivantes : "
            f"{recent}."
        )

    system_content = f'{cfg.persona}\n\n{rules}'
    user_content = _facts_to_text(facts)

    messages = [
        {'role': 'system', 'content': system_content},
        {'role': 'user', 'content': user_content},
    ]

    try:
        url = _endpoint(cfg.provider)
        if url is None:
            return None

        resp = requests.post(
            url,
            json={
                'model': cfg.model,
                'messages': messages,
                'temperature': cfg.temperature,
                'max_tokens': cfg.max_tokens,
            },
            headers={
                'Authorization': f'Bearer {cfg.api_key}',
                'Content-Type': 'application/json',
            },
            timeout=15,
        )
        resp.raise_for_status()

        content = resp.json()['choices'][0]['message']['content']
        cleaned = _clean(content)
        return cleaned or None
    except Exception:
        return None
