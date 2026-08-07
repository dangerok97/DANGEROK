# Facts, Hypotheses, Decisions

## Facts

Solo info **confermate**: documento verificato, utente, calendario, (futuro) email/banking/whatsapp, conversazione confermata, edit manuale.

Campi chiave: `id`, `type`, `value`, `source`, `source_id`, `confidence`, `verified`, `verified_by`, `verified_at`, `created_at`, `updated_at`, `origin`, `version`, `explanation`, `ai_summary`, `status` (`current`|`superseded`|`archived`), `superseded_by`, `superseded_at`, `active`.

### Regole

- **Mai cancellare** un Fact.
- Fact verificati non si modificano in silenzio: nuovo valore → **supersede** (vecchio resta).
- Hypothesis **non** è mai trattata come Fact finché non confermata.

## Hypotheses

Ciò che ORA pensa: `confidence`, `reason`, `evidence`, `missing_information`, `question_to_confirm`, `status` (`active`|`confirmed`|`rejected`|`expired`).

- Confirm → crea Fact (eventuale supersede) + hypothesis `confirmed`
- Reject → `rejected` (nessun Fact)
- **Mai auto-promozione**

## Decisions

Suggerimenti importanti elevati a Decision:

`decision_id`, `life_object_id`, `reason`, `benefit`, `risk`, `alternatives`, `ai_reasoning`, `user_choice`, `outcome` (`pending`|`accepted`|`rejected`|`postponed`|`completed`|`dismissed`|`never_ask_again`), `decision_date`, `review_date`, `fingerprint`.

Se `rejected` / `never_ask_again` → fingerprint memorizzato; non riproposto (filtro quiet su questions/suggestions).

## Separazione AI (prompt)

Gemini deve sempre rispondere con sezioni **distinte**:

1. Facts  
2. Hypotheses  
3. Questions  
4. Recommendations  
5. Decisions  

Mai mischiare. `invented_facts=false`. Backend = autorità.

## Goals

Solo link: `LifeObject.goals: List[str]` + `goal.life_object_id`. Non duplicare il Goal Engine.
