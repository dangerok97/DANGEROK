"""Administrative / financial structured extraction (local, grounded)."""
from __future__ import annotations

import re
from typing import Optional

from documents.intelligence.schemas import AdminAnalysis


def _labeled(text: str, labels: tuple[str, ...]) -> Optional[str]:
    for lab in labels:
        m = re.search(rf"{re.escape(lab)}\s*[:\-]\s*(.+)", text, re.I)
        if m:
            return m.group(1).strip()[:240]
    return None


def build_admin_analysis(text: str, *, macro: str, amounts: list | None = None) -> Optional[AdminAnalysis]:
    if macro not in ("administrative", "financial", "receipt", "contract", "legal"):
        # still allow invoice-like heuristics
        blob = (text or "").lower()
        if not any(k in blob for k in ("fattura", "ricevuta", "scadenza", "importo", "contratto", "prot.")):
            return None
    sender = _labeled(text, ("Mittente", "Fornitore", "Emittente", "Da"))
    recipient = _labeled(text, ("Destinatario", "Cliente", "A"))
    subject = _labeled(text, ("Oggetto", "Descrizione", "Causale"))
    number = _labeled(text, ("Numero", "N. fattura", "Fattura n", "Prot.", "Riferimenti", "Riferimento"))
    due = _labeled(text, ("Scadenza", "Data scadenza", "Entro il", "Data limite"))
    issue = _labeled(text, ("Data", "Data emissione", "Emessa il"))
    payment = _labeled(text, ("Pagamento", "Modalità di pagamento", "Metodo di pagamento"))
    action = _labeled(text, ("Azione richiesta", "Richiesta", "Si invita a"))
    amount = None
    currency = None
    if amounts:
        a0 = amounts[0]
        if isinstance(a0, dict):
            amount = str(a0.get("amount") or "")
            currency = a0.get("currency")
        else:
            amount = str(a0)
    if not amount:
        m = re.search(r"(\d+[.,]\d{2})\s*(€|EUR|euro)?", text or "", re.I)
        if m:
            amount = m.group(1)
            currency = m.group(2) or "EUR"
    actions = [action] if action else []
    expl_parts = []
    if subject:
        expl_parts.append(f"Il documento riguarda: {subject}.")
    if amount:
        expl_parts.append(f"Importo indicato: {amount} {currency or ''}.".strip())
    if due:
        expl_parts.append(f"Scadenza: {due}.")
    if action:
        expl_parts.append(f"Azione richiesta: {action}.")
    if not expl_parts:
        expl_parts.append("Documento amministrativo/finanziario: verifica i campi estratti.")
    return AdminAnalysis(
        sender=sender,
        recipient=recipient,
        subject=subject,
        document_number=number,
        amount=amount,
        currency=currency,
        issue_date=issue,
        due_date=due,
        payment_method=payment,
        required_actions=actions,
        simple_explanation=" ".join(expl_parts),
        urgency="soon" if due else "upcoming",
        priority="high" if due or action else "medium",
        confidence=0.65 if (due or amount or subject) else 0.4,
    )
