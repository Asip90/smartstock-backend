"""Constructeurs de faits (purs) pour le moteur de notifications IA.

Ces fonctions ne font QUE lire Firestore et renvoyer des dicts de nombres
(ou de chaînes simples). Aucune mise en forme, aucun appel LLM, aucun envoi
de push : ça, c'est le travail du moteur de notifications et du service IA
(qui consomment ces faits).

Toutes les fonctions prennent un client Firestore `db` en paramètre (au lieu
d'appeler `firebase_service.db()` elles-mêmes) afin d'être testables avec un
faux client en mémoire.
"""
from datetime import datetime, time, timedelta

from django.utils import timezone

DEFAULT_THRESHOLD = 5  # repli si nbreCritique non défini (aligné sur l'app)


def _low_stock(db, shop_id: str):
    """Renvoie la liste ``(nom, quantite)`` des produits sous le seuil critique,
    triée par quantité croissante (les plus critiques en premier)."""
    low = []
    for p in db.collection('produits').where('shopId', '==', shop_id).stream():
        pd = p.to_dict() or {}
        qty = pd.get('quantity', 0) or 0
        threshold = pd.get('nbreCritique') or DEFAULT_THRESHOLD
        if qty <= threshold:
            low.append((pd.get('name', 'Produit'), qty))
    low.sort(key=lambda x: x[1])
    return low


def evening_facts(db, shop_id: str, shop_data: dict) -> dict:
    """Faits du bilan du soir : ventes du jour (nombre, CA, encaissé, crédit).

    Reprend l'agrégation de ``send_daily_summary`` sur la journée en cours.
    """
    now = timezone.localtime()
    start = timezone.make_aware(datetime.combine(now.date(), time.min))

    revenue = 0.0
    cash = 0.0
    count = 0
    sales = (db.collection('sales')
             .where('shopId', '==', shop_id)
             .where('saleDate', '>=', start)
             .stream())
    for s in sales:
        sd = s.to_dict() or {}
        total = float(sd.get('totalAmount', 0) or 0)
        paid = sd.get('amountPaid')
        paid = float(paid) if paid is not None else total
        revenue += total
        cash += paid
        count += 1

    credit = revenue - cash

    return {
        'shop_name': shop_data.get('name', 'votre boutique'),
        'count': count,
        'revenue': revenue,
        'cash': cash,
        'credit': credit,
    }


def stock_facts(db, shop_id: str, shop_data: dict) -> dict:
    """Faits de l'alerte stock critique : nombre de produits bas + échantillon.

    Reprend la logique de ``send_stock_alerts`` (seuil ``nbreCritique`` ou
    repli ``DEFAULT_THRESHOLD``).
    """
    low = _low_stock(db, shop_id)

    return {
        'shop_name': shop_data.get('name', 'votre boutique'),
        'count': len(low),
        'samples': [name for name, _ in low[:3]],
    }


def morning_facts(db, shop_id: str, shop_data: dict) -> dict:
    """Faits du briefing du matin : bilan d'hier, ruptures actuelles,
    meilleur produit d'hier (si calculable) et clients à relancer (si
    calculable).

    - ``yesterday_count`` / ``yesterday_revenue`` : ventes d'hier (00h-00h).
    - ``ruptures_count`` / ``ruptures_samples`` : produits sous le seuil
      critique, à l'instant présent (réutilise ``stock_facts``).
    - ``best_seller`` : nom du produit le plus vendu (en quantité) hier,
      uniquement si les documents de vente contiennent une liste d'articles
      exploitable ; sinon la clé est omise.
    - ``debts_count`` / ``debts_total`` : nombre de clients avec un solde
      impayé et la somme de ces soldes, lus dans la collection ``credits`` ;
      omis si la collection est vide, absente ou si la lecture échoue.
    """
    now = timezone.localtime()
    start_of_today = timezone.make_aware(datetime.combine(now.date(), time.min))
    start_of_yesterday = start_of_today - timedelta(days=1)

    yesterday_count = 0
    yesterday_revenue = 0.0
    product_quantities = {}
    has_items_data = False

    sales = (db.collection('sales')
             .where('shopId', '==', shop_id)
             .where('saleDate', '>=', start_of_yesterday)
             .where('saleDate', '<', start_of_today)
             .stream())
    for s in sales:
        sd = s.to_dict() or {}
        total = float(sd.get('totalAmount', 0) or 0)
        yesterday_revenue += total
        yesterday_count += 1

        items = sd.get('items')
        if isinstance(items, list):
            for item in items:
                if not isinstance(item, dict):
                    continue
                name = item.get('name') or item.get('productName')
                qty = item.get('quantity', item.get('qty', 0)) or 0
                if not name:
                    continue
                try:
                    qty = float(qty)
                except (TypeError, ValueError):
                    continue
                has_items_data = True
                product_quantities[name] = product_quantities.get(name, 0) + qty

    facts = {
        'shop_name': shop_data.get('name', 'votre boutique'),
        'yesterday_count': yesterday_count,
        'yesterday_revenue': yesterday_revenue,
    }

    # Ruptures actuelles (réutilise la même logique que stock_facts).
    low = _low_stock(db, shop_id)
    facts['ruptures_count'] = len(low)
    facts['ruptures_samples'] = [name for name, _ in low[:3]]

    if has_items_data and product_quantities:
        best_seller = max(product_quantities.items(), key=lambda kv: kv[1])[0]
        facts['best_seller'] = best_seller

    # Clients à relancer (crédits impayés) : dégradation propre si absent.
    try:
        debts_count = 0
        debts_total = 0.0
        found_any = False
        for c in db.collection('credits').where('shopId', '==', shop_id).stream():
            found_any = True
            cd = c.to_dict() or {}
            balance = cd.get('balance')
            if balance is None:
                total = float(cd.get('totalAmount', 0) or 0)
                paid = float(cd.get('amountPaid', 0) or 0)
                balance = total - paid
            balance = float(balance or 0)
            if balance > 0:
                debts_count += 1
                debts_total += balance

        if found_any:
            facts['debts_count'] = debts_count
            facts['debts_total'] = debts_total
    except Exception:
        pass

    return facts


def first_name(db, uid: str) -> str:
    """Renvoie le premier prénom de l'utilisateur ``users/{uid}``.

    Lit le champ ``name`` ou ``displayName`` et renvoie son premier mot.
    Renvoie ``''`` si le document est introuvable, vide, ou en cas d'erreur.
    """
    try:
        doc = db.collection('users').document(uid).get()
        if not doc.exists:
            return ''
        data = doc.to_dict() or {}
        full_name = data.get('name') or data.get('displayName') or ''
        full_name = str(full_name).strip()
        if not full_name:
            return ''
        return full_name.split()[0]
    except Exception:
        return ''
