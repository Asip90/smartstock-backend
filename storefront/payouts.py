"""Traitement des demandes de retrait (`payoutRequests`) — solde des ventes
en ligne reversé au propriétaire de boutique. Semi-automatique : jamais
déclenché sans validation humaine (page admin dédiée,
`storefront/payout_admin.py`) — cf. design solde & retraits."""
from billing import fedapay
from billing import firebase_service as fb


def _split_name(shop_name: str) -> tuple[str, str]:
    """FedaPay exige prénom/nom pour le bénéficiaire du payout — la boutique
    n'a qu'un nom unique, on le découpe au mieux (repli sûr si vide)."""
    parts = (shop_name or 'Boutique').strip().split(' ', 1)
    firstname = parts[0] or 'Boutique'
    lastname = parts[1] if len(parts) > 1 else firstname
    return firstname, lastname


def get_pending_payout_requests() -> list[dict]:
    """Demandes `pending`, enrichies du nom de la boutique (pour l'affichage
    dans la page admin)."""
    db = fb.db()
    docs = db.collection('payoutRequests').where('status', '==', 'pending').stream()
    results = []
    for doc in docs:
        data = doc.to_dict()
        shop_doc = db.collection('shops').document(data['shopId']).get()
        shop_name = shop_doc.to_dict().get('name', '') if shop_doc.exists else ''
        results.append({'id': doc.id, 'shopName': shop_name, **data})
    return results


def approve_and_send(request_id: str) -> tuple[bool, str]:
    """Appelle FedaPay pour envoyer le montant demandé, puis écrit le
    résultat sur le document. Idempotent : refuse si la demande n'est plus
    `pending` (déjà traitée)."""
    db = fb.db()
    req_ref = db.collection('payoutRequests').document(request_id)
    req_doc = req_ref.get()
    if not req_doc.exists:
        return False, 'demande introuvable'
    data = req_doc.to_dict()
    if data.get('status') != 'pending':
        return False, f"déjà traitée (statut: {data.get('status')})"

    shop_doc = db.collection('shops').document(data['shopId']).get()
    shop_data = shop_doc.to_dict() if shop_doc.exists else {}
    firstname, lastname = _split_name(shop_data.get('name', ''))

    try:
        result = fedapay.create_payout(
            amount=data['amountRequested'],
            firstname=firstname,
            lastname=lastname,
            phone_number=data['phoneNumber'],
            phone_country=data['phoneCountry'],
            currency=shop_data.get('currency', 'XOF'),
        )
    except Exception as e:
        req_ref.update({
            'status': 'failed',
            'adminNote': str(e),
            'processedAt': fb.firestore.SERVER_TIMESTAMP,
        })
        return False, str(e)

    req_ref.update({
        'status': 'sent',
        'fedapayPayoutId': result['fedapay_id'],
        'feesAmount': result['fees'],
        'amountSent': result['amount_transferred'],
        'totalDeducted': result['amount_debited'],
        'processedAt': fb.firestore.SERVER_TIMESTAMP,
    })
    return True, 'ok'


def reject(request_id: str, note: str) -> bool:
    """Rejette une demande `pending` (ex. numéro invalide) — aucun appel
    FedaPay. Idempotent, comme [approve_and_send]."""
    db = fb.db()
    req_ref = db.collection('payoutRequests').document(request_id)
    req_doc = req_ref.get()
    if not req_doc.exists or req_doc.to_dict().get('status') != 'pending':
        return False
    req_ref.update({
        'status': 'rejected',
        'adminNote': note,
        'processedAt': fb.firestore.SERVER_TIMESTAMP,
    })
    return True
