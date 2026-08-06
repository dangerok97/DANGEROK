# Life Setup — Product

Ultimo aggiornamento: 2026-08-06 — foundation AI-driven first-launch conversation.

## Cos’è

La **prima conversazione** con ORA dopo la registrazione. Non è un onboarding wizard, non è un questionario, non è una sezione Impostazioni permanente.

ORA ascolta, propone la prossima domanda utile (o un documento da caricare), spiega il beneficio concreto, e costruisce un Life Profile per dominio. Poi il modulo **scompare per sempre** come superficie dedicata.

## Cosa non è

- Wizard a step / progress bar obbligatoria  
- Form «Completa il profilo»  
- Sezione Home o Profilo «Life Setup»  
- Open Banking / Email / WhatsApp / Weather (solo stub onesti)

## Flusso utente

1. Nuovo utente → conversazione naturale (filosofia collaborativa, ~10–15 min indicativi).  
2. Skip / posticipa dominio / esci in qualsiasi momento.  
3. Esempio: «Ho comprato casa.» → ORA preferisce il **rogito** → extract → Life Graph / Profile / Goal Casa → domanda sul mutuo.  
4. Completato / interrotto / saltato → `should_show=false`, `module_visible=false`.  
5. Ripresa gentile: **una** suggestion Proactive/Home («ORA può aiutarti ancora di più») — mai «Completa il profilo» / «Life Setup».

## Conoscenza successiva

Conversation Engine, Documents V2, Goals, Proactive — non un form di setup.

## Feature flags

- `LIFE_SETUP_ENABLED` (default ON in locale)  
- `AI_LIFE_STRATEGIST_ENABLED` (default ON in locale)

## API

`/api/life-setup/start|status|skip|answer|upload-doc|explain|complete|cancel`  
(+ view/correct/delete profilo utente)

## Privacy

Contesto proporzionato. Mai password / PIN / OTP / credenziali bancarie. L’utente può vedere, correggere, cancellare i fatti del Life Profile. L’AI non può cancellare né sovrascrivere fatti confermati.
