# ORA — Intelligent Documents Architecture

Branch: `feature/intelligent-documents`  
Data: 2026-08-05

## 1. Architettura attuale (pre)

- Upload sync → storage locale → Mongo `documents` → Life Graph + Knowledge
- Extraction sync (PDF/OCR/text) in `documents/extraction.py`
- Insights on-read: `compute_insights` (classificazione deterministica + campi)
- Nessuna pipeline a stati, nessun event candidate persistito, nessun calendario interno server-side
- LLM adapter `backend/llm` non usato dai documenti

## 2. Elementi riutilizzabili

- `DocumentService.upload` / storage / auth isolation
- `ExtractionPipeline`, classifier, field_resolver, insights
- `llm.chat_completion` (opzionale)
- Knowledge merge + Life Graph nodes
- FE detail tabs + DocumentActionsBar

## 3. Elementi mancanti (questo intervento)

- Stati pipeline + worker locale
- Tassonomia estensibile macro/sub
- Analysis persistita (DOCUMENT_ANALYSIS, EVENT_CANDIDATE, EDUCATION)
- Calendar draft interno provider-agnostic
- UI conferma evento / studio / progress
- Consenso AI documenti

## 4. Rischi

- LLM assente → analisi locale solo (non spacciare per AI completa)
- OCR dipendente da Tesseract sul host
- Worker in-process: non multi-istanza
- Privacy: testo inviato a provider solo se consenso + LLM configurato

## 5. Piano

1. Persistenza stati + job queue locale
2. Analyzer locale + LLM JSON opzionale
3. API analyze / events / calendar
4. FE sezioni dinamiche
5. Test fixture sintetiche
