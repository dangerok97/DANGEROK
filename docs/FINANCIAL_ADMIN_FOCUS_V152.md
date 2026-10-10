# ORA v152 — Le fonti lette non sono compiti da organizzare

Il Focus mobile «Admin: Conosco un pagamento entro fine mese» può provenire da un vecchio progetto Action Engine, non da un pagamento identificato. La v147 escludeva i progetti senza riferimenti; rimaneva però un caso: bastava un documento semplicemente collegato per far riapparire la card come lavoro, anche senza task, promemoria, decisioni o eventi.

## Correzione
Il progetto entra nelle proposte di Focus solo quando esiste almeno un riferimento a **un compito, una decisione, un promemoria o un evento**. I documenti allegati restano conservati come fonti, ma non bastano a generare un incarico. La sessione attiva resta riprendibile dal suo elenco indipendente. I progetti con lavoro reale continuano a essere accessibili, e la categoria `admin` non viene spacciata automaticamente per una bolletta.

## Regressione
Aggiunta la fixture «document_only» in `test_financial_email_grounding_v147.py`; verifica che un documento e una sessione non generino un Focus amministrativo, e che un progetto con `task_ids` mantenga l'azione. Lo stesso test è già parte della CI.

Non modifica contenuti email, importi, date, memorie o la configurazione bancaria. Non elimina il progetto dal database.
