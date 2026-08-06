# Conversation Experience — Life Experience

## UX

- Bolle conversazionali (ORA / utente)
- Una domanda visibile per turno
- Beneficio in italiano sotto la domanda («Perché me lo chiedi?»)
- Azioni: rispondi, carica documento consigliato, salta tema, più tardi, esci
- **Nessuna** progress bar, step wizard, form multi-campo

## Copy (italiano)

| Momento | Esempio |
|---------|---------|
| Saluto | «Ciao — sono ORA. Non ti farò un questionario…» |
| Domanda | Decisa dallo Strategist / fallback |
| Beneficio | «ORA può ricordarti le rate del mutuo…» |
| Home | «Adesso posso seguire il tuo mutuo.» |
| Proactive | «Posso ricordarti la prossima rata del mutuo…» |
| Interrupt | «ORA può aiutarti ancora di più» |
| Wrap | Senza menzionare «Life Setup» come sezione |

## Anti-pattern vietati

- «Completa il profilo»
- «Life Setup» come CTA
- Due domande nella stessa bolletta
- Questionario a scelta multipla obbligatorio

## Route

`/life-setup` resta il path tecnico (compatibilità gate/login).
L’esperienza prodotto è **Life Experience** (`ui.experience = life_experience`).
