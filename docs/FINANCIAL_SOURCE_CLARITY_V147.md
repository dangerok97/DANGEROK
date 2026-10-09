# v147 — Le email economiche devono diventare informazioni chiare

Data 9 ottobre 2026. Riferimento: quattro screenshot iPhone dell'utente.

## Riscontri osservati
- Un messaggio ING sulla carta di credito comunica un addebito mensile il 10 ottobre, **non comunica l'importo** e indica di consultare l'app o l'estratto conto ING. Non è un nuovo pagamento autonomo da organizzare, né si può attribuire alla carta l'importo di un movimento del conto.
- Una comunicazione iCloud+ da 50 GB indica **€0,99 mensili** e una decorrenza `2026-10-11 03:25:28 America/Los_Angeles`, che corrisponde alle ore 12:25 italiane dell'11 ottobre 2026 (CEST). Non alla data che si ricaverebbe arrotondando il titolo «tra due giorni».
- Le cifre €760 e €14,99 viste in Conti e denaro non sono automaticamente la carta ING o il rinnovo iCloud.
- «Mock ASPSP» con saldo €3.250 è una sorgente di test/sandbox, non liquidità spendibile.
- La card «Admin: Conosco un pagamento entro fine mese» nasce da un hint del vecchio Action Engine promosso a Focus, non da un pagamento identificato e azionabile.

## Modifiche
1. Action Engine: una semplice `next_focus_hint` non è un lavoro. I progetti possono diventare azioni Home solo con una ragione di lavoro esplicita e già verificata; `admin` non equivale automaticamente a `bill`. Il piano resta conservato in Action Engine.
2. Connected Life: l'estratto privato già letto su richiesta del ragionamento segue il segnale fino al motore finanziario **solo in memoria**, evitando il secondo ragionamento fatto sul titolo impoverito. Non vengono memorizzati né stampati i corpi delle email.
3. Interpretazione finanziaria: il prompt distingue l'addebito complessivo di una carta senza cifra, gli abbonamenti con canone esplicito e i movimenti bancari non identificati. L'importo assente resta `None`, non €0.
4. Date: quando una scadenza è stata riconosciuta e la fonte contiene **un solo timestamp esplicito con fuso IANA**, questo timestamp prevale sulla data relativa approssimata nel titolo; non crea date se non è stata riconosciuta un'obbligazione.
5. Fonte: la schermata finanziaria usa i metadati dell'email originaria — oggetto, ma non corpo — tramite riferimento owner-scoped, così anche un fatto storico genericamente chiamato «Qualcosa di economico» mostra da quale email deriva. Niente identità del pagamento inferite da somiglianze.
6. Banca: l'ambiente provider (`simulated` / `real`) si conserva su ogni nuova lettura. Il frontend mostra «Conto di prova» e «Saldo simulato» per simulazioni, anche nel caso già osservato `Mock ASPSP`. I movimenti conosciuti dalla sola prova non vengono presentati come spese reali.

## Confini
Questa v147 migliora il percorso delle **nuove** email lette per un giudizio economico e il contesto visualizzato per i dati già registrati. Non falsifica l'importo dell'email ING, non mette in relazione €760 con ING né €14,99 con iCloud senza fonte esatta; non cancella né sovrascrive automaticamente vecchie memorie/fatti economici. Per ricalcolare i fatti storici con tutti i loro dettagli serve una rivalutazione verificata della fonte originale e un passaggio di governance, non una sostituzione cosmetica del testo.
