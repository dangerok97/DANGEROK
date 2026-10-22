# ORA Cucina — pianificazione e lista della spesa (fase 2)

Questa fase aggiunge un piano settimanale proprietario e una lista della spesa
derivata dalle ricette salvate. Non altera il ricettario della fase 1.

## API (autenticazione ORA obbligatoria)

- `GET /api/cooking/plan?week_start=YYYY-MM-DD` — legge il piano (lunedì richiesto).
- `PUT /api/cooking/plan` — salva il piano con revisione ottimistica; ogni ricetta deve appartenere all'utente.
- `GET /api/cooking/shopping-list?week_start=YYYY-MM-DD` — genera la lista dalle ricette pianificate.
- `PUT /api/cooking/shopping-list/{item_id}?week_start=YYYY-MM-DD` — spunta/despunta un articolo.
- `POST /api/cooking/shopping-list/manual?week_start=YYYY-MM-DD` — aggiunge un articolo manuale.

Esempio di piano:

```json
{
  "week_start": "2026-10-19",
  "revision": 0,
  "household_size": 2,
  "budget_eur": 70,
  "preferences": ["italiana", "rapida"],
  "slots": [
    {"day": 0, "meal": "dinner", "recipe_id": "0123456789abcdef0123456789abcdef", "servings": 2}
  ]
}
```

## Garanzie e limiti

- Dati isolati per utente; le ricette di altri utenti sono rifiutate.
- Il piano usa revisione compare-and-swap per evitare sovrascritture silenziose.
- La lista conserva le spunte per articoli con la stessa ricetta e riga ingrediente.
- Quantità e ingredienti sono riportati come nella ricetta: niente conversioni o
  somme ambigue, nessuna sottrazione dalle scorte finché la dispensa non esiste.
- Le categorie sono euristiche e modificabili nel futuro; non sono informazioni nutrizionali.
- Questa fase API non genera ancora menu con AI, non conosce le allergie né i prezzi reali
  dei supermercati e non è ancora collegata a WhatsApp. Non dichiarare tali funzioni disponibili.

## Verifiche locali

```bash
cd backend
pytest -q cooking_planner/tests
```
