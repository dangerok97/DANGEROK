# ORA v154 — La chat non deve abbandonare una telefonata preparata

Segnalazione: ORA chiede il recapito del destinatario, riceve il numero e alla successiva richiesta di chiamare risponde con la frase generica «Sto ancora ragionando». Questa frase proveniva dalla conclusione di un ciclo AI senza risposta utile e non certificava alcuna lavorazione in corso.

## Correzioni

- Se la funzione telefonica è stata davvero invocata, viene mostrata la sua frase completa, anche quando finisce il budget del modello.
- Una risposta breve continua la preparazione già associata alla sessione e allo stesso utente, senza crearne un'altra.
- Un numero scritto da solo, durante la preparazione, è solo un candidato da registrare e **confermare**: non dà permesso a chiamare.
- Al limite di ragionamento, ORA legge la domanda ancora aperta, oppure espone il mancato completamento. Non promette di stare ancora lavorando.
- Dopo la lettura del riepilogo, «non aggiungo altro, chiama» è un sì alla richiesta di chiamata; non è, e non diventa, un sì al numero.

## Limiti e sicurezza

La telefonata non deve iniziare quando il numero è sconosciuto, non confermato, associato a un'altra persona, quando il provider non è pronto o quando manca il via libera finale al riepilogo visto in un turno precedente. I test usano dati fittizi, senza accesso a dispositivi o carrier. La verifica sul proprio account rimane distinta dalla CI e non va dichiarata completata finché non avviene.
