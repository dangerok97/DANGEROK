# Life Document Mapping

Branch: `feature/life-experience-ai-documents`

## Cos'è

Mapper dichiarativi che trasformano un `DocumentReasoning` (AI Document Understanding) in campi del **Life Profile**, con provenienza completa. Mai un secondo storage: i campi vivono in `LifeProfileService` (stesso store di Life Setup/Life Experience).

Modulo: `backend/life_setup/document_mapping.py`

## `MappedField`

```python
MappedField(domain, key, value, raw_value=None, confidence=0.5, source_page=None, label="", status="")
```

`status` è calcolato automaticamente da `status_for_confidence(confidence)` se non specificato.

## Soglie di confidenza → comportamento UI

| Soglia | Valore default | Status risultante | Comportamento UI |
|---|---|---|---|
| Alta | `≥ 0.80` (`LIFE_DOC_CONFIDENCE_HIGH`) | `extracted` | Auto-uso, mostrato in **"Dati trovati"** |
| Media/bassa | `< 0.80` (`LIFE_DOC_CONFIDENCE_MEDIUM=0.50` come riferimento) | `suggested` | Mostrato in **"Dati da verificare"** — richiede conferma/correzione esplicita |

Configurabile via env: `LIFE_DOC_CONFIDENCE_HIGH`, `LIFE_DOC_CONFIDENCE_MEDIUM`.

## Mapper per tipo documento

| Funzione | `document_type` | Campi Life Profile prodotti |
|---|---|---|
| `map_rogito` | `rogito` | `casa.owned`, `casa.purchased`, `doc.rogito`, `casa.indirizzo`, `casa.valore_acquisto`, `casa.data_rogito`, `casa.tipo_immobile` |
| `map_contratto_locazione` | `contratto_locazione` | `casa.owned=False`, `casa.affitto`, `doc.contratto_locazione`, `casa.indirizzo`, `casa.affitto_scadenza` |
| `map_mutuo` | `mutuo` | `casa.mutuo`, `doc.mutuo`, `casa.mutuo_istituto`, `casa.mutuo_importo`, `casa.mutuo_rata`, `casa.mutuo_scadenza` |
| `map_bolletta` | `bolletta` | `casa.utenze`, `doc.bolletta`, `casa.bolletta_fornitore`, `casa.bolletta_tipo`, `casa.bolletta_importo`, `casa.bolletta_scadenza` |
| `map_libretto` | `libretto` | `auto.owned`, `doc.libretto`, `auto.targa`, `auto.modello`, `auto.telaio`, `auto.immatricolazione` |
| `map_polizza` | `polizza_auto` / `polizza_casa` / altro | `auto.assicurazione` o `casa.assicurazione` o `assicurazioni.tipo`, `*.polizza_compagnia`, scadenza specifica per dominio |
| `map_prestito_auto` | `prestito_auto` | `auto.finanziamento`, `auto.finanziamento_rata`, `auto.finanziamento_scadenza` |
| `map_piano_di_studi` | `piano_di_studi` | `studio.active`, `doc.piano_di_studi`, `studio.universita`, `studio.corso`, `studio.esami`, `studio.anno_accademico` |
| `map_dispensa` | `dispensa` | `studio.active`, `doc.dispensa`, materia/argomento |

Ogni mapper produce sempre almeno i campi booleani "è successo" (es. `doc.rogito=True`) con la confidenza del documento, e opzionalmente campi di dettaglio **solo se il modello li ha estratti** — mai campi vuoti forzati.

## Provenienza (mai sovrascrivere il confermato)

`LifeProfileService.upsert_fact` / `apply_mapped_fields` (in `backend/life_setup/profile_service.py`) applicano questa regola:

- Se il campo esistente ha `status in {confirmed, corrected}` → il nuovo valore estratto **non lo sovrascrive mai**; se il nuovo valore diverge, viene aperta una **pending confirmation** (vedi `CROSS_DOCUMENT_REASONING.md`) invece di sovrascrivere silenziosamente.
- Ogni campo applicato porta: `source_document_id`, `confidence`, `provider`, `model`, `analysis_version`, `raw_value`, timestamp di estrazione.
- `confirm_field` / `correct_field` / `reject_field` sono le uniche azioni utente che cambiano `status` verso `confirmed` / `corrected` / `rejected`.

## Status enum completo

`extracted` → `suggested` → (`confirmed` | `corrected` | `rejected`), tracciato per singolo campo, mai per l'intero documento.
