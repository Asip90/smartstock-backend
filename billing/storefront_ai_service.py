"""Génération des textes de section (hero/à propos/SEO) de la boutique en
ligne, en français ET en anglais, à partir des données réelles de la
boutique. Réutilise la config IA existante (`AIConfig`, déjà pilotée depuis
Jazzmin pour les notifications) mais avec son propre prompt — jamais couplé
à `ai_service.py`, qui reste dédié aux notifications."""
import json

import requests

from .models import AIConfig

_MAX_PRODUCTS_SAMPLE = 20

_SYSTEM_PROMPT = (
    "Tu rédiges le contenu d'un site vitrine e-commerce pour une boutique "
    "en Afrique de l'Ouest. Génère les textes en FRANÇAIS ET EN ANGLAIS, ton "
    "commercial mais sobre, orienté référencement local (ville/quartier si "
    "fourni), sans emphase excessive, sans emoji. Réponds STRICTEMENT en "
    "JSON avec exactement les clés suivantes, toutes des chaînes non vides : "
    "heroTitle_fr, heroTitle_en, heroSubtitle_fr, heroSubtitle_en, "
    "aboutText_fr, aboutText_en, seoDescription_fr, seoDescription_en."
)

_REQUIRED_KEYS = (
    'heroTitle_fr', 'heroTitle_en', 'heroSubtitle_fr', 'heroSubtitle_en',
    'aboutText_fr', 'aboutText_en', 'seoDescription_fr', 'seoDescription_en',
)


def _endpoint(provider: str) -> str | None:
    if provider == 'mistral':
        return 'https://api.mistral.ai/v1/chat/completions'
    if provider == 'openrouter':
        return 'https://openrouter.ai/api/v1/chat/completions'
    return None


def _build_user_message(shop_name, shop_description, products, location) -> str:
    lines = [f'Nom de la boutique : {shop_name}']
    if location:
        lines.append(f'Localisation : {location}')
    if shop_description:
        lines.append(f'Description : {shop_description}')
    sample = products[:_MAX_PRODUCTS_SAMPLE]
    if sample:
        lines.append('Échantillon de produits :')
        for p in sample:
            lines.append(f"- {p.get('name', '')} ({p.get('category', '')}) : {p.get('description', '')}")
    return '\n'.join(lines)


def generate_storefront_content(
    *, shop_name: str, shop_description: str, products: list[dict], location: str,
) -> dict | None:
    """Renvoie un dict avec les 8 clés bilingues, ou None si l'IA est
    désactivée/mal configurée/indisponible (jamais d'exception)."""
    cfg = AIConfig.get_solo()
    if not cfg.enabled or not cfg.api_key:
        return None

    url = _endpoint(cfg.provider)
    if url is None:
        return None

    try:
        resp = requests.post(
            url,
            json={
                'model': cfg.model,
                'messages': [
                    {'role': 'system', 'content': _SYSTEM_PROMPT},
                    {'role': 'user', 'content': _build_user_message(
                        shop_name, shop_description, products, location)},
                ],
                'temperature': 0.7,
                'max_tokens': 600,
                'response_format': {'type': 'json_object'},
            },
            headers={
                'Authorization': f'Bearer {cfg.api_key}',
                'Content-Type': 'application/json',
            },
            timeout=20,
        )
        resp.raise_for_status()
        content = resp.json()['choices'][0]['message']['content']
        data = json.loads(content)
        if not all(key in data for key in _REQUIRED_KEYS):
            return None
        return {key: data[key] for key in _REQUIRED_KEYS}
    except Exception:
        return None
