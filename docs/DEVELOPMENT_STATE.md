# ORA — Development State



Last updated: 2026-08-06 (AI document understanding v2 deepen)



## Branch



- Active: `feature/life-experience-ai-documents` (local commit `42e3cc2`; no push)
- Tip base before this work: `36da3b6`



## AI Document Understanding v2 (this batch)



| Item | Stato |

|------|--------|

| `analysis_version` bug (`int("2.0")`) | **fixed** — schema string vs revision int separated (`versions.py` + migration heal) |

| Document Reasoner + life context (profile/goals/calendar/brain/docs) | **implemented** |

| Structured fields: context/benefit/actions/knowledge/priority/deadlines/related_docs | **implemented** |

| Life Profile hypotheses (bolletta → energia + ownership suggested) | **implemented** — never overwrite confirmed |

| Cross-document affinity (casa/auto/studio) | **strengthened** |

| AI-first «Cosa posso fare» + reminder titles with supplier | **implemented** |

| Brain/Knowledge memory persist (best-effort, no dupes) | **implemented** |

| Gemini prompt rewrite (assistant/secretary, no invent) | **implemented** |

| Synthetic fixture tests + analysis_version regression | **added** |

| Gemini live smoke (≥2 new types) | **optional** — skip senza `GEMINI_API_KEY` (dichiarato onesto) |

| Playwright bolletta (+ CASA/AUTO invariati) | **updated** (azioni + titolo + profile check) |

| GitHub Actions CI | **added** `.github/workflows/ci.yml` |

| Mobile native DocumentPicker | **NOT verified** |



## Prior on this branch (still valid)



| Item | Stato |

|------|--------|

| Real Expo file picker + Documents V2 upload | **implemented** |

| Gemini verified historically for rogito/bolletta/libretto/piano | **yes** (sessioni precedenti) |

| Draft-only deadline events + confirm | **implemented** |



## Open / next



1. Eseguire smoke Gemini reale su contratti telefono/busta paga quando la chiave è disponibile e registrare evidence

2. Playwright full path Goal/Brain UI (API profile checked; UI Brain dedicata ancora assente)

3. Mobile nativo DocumentPicker

4. Non aggiungere Email / Open Banking / WhatsApp / Weather come integrazioni reali qui



## Credentials / safety



- Never commit `.env` / tokens

- CI green senza secret a pagamento; Gemini gated

- AI cannot delete profile facts or overwrite confirmed values



