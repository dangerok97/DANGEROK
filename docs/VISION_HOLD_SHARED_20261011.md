# Vision: schema persistente, X e catalogo automatico

Requisiti del feedback del 11 ottobre 2026.

Dopo un riconoscimento riuscito il modello rimane fissato nello spazio dello schermo.
Perdita di aggancio, spostamento della fotocamera e oggetto fuori scena non lo nascondono.
Scansioni automatiche sospese mentre si esplora: selezione, rotazione e ricomposizione restano disponibili.
La X visibile (46px, etichetta accessibile) chiude il modello e riavvia il riconoscimento
senza chiudere il MediaStream. Risposte tardive sono invalidate. Dall'anteprima catalogo
la X apre la fotocamera su richiesta esplicita. Spegni e uscita fermano ancora la fotocamera.

Non esiste più una casella per contribuire. Il server salva automaticamente i nuovi schemi
generici validati nel catalogo comune; anche i vecchi client che inviano contribute=false
non creano nuovi schemi privati. Il generatore continua a ricevere la sola famiglia generica,
non foto, identità, seriali o contesto privato. Le foto non vengono archiviate nel catalogo.
Le vecchie voci private non vengono ripubblicate o migrate. Non è addestramento dei pesi AI.

Test aggiornati: schema ancora visibile dopo 17 secondi senza oggetto, assenza di nuove
scansioni finché non si preme X, X senza nuova richiesta getUserMedia, schemi condivisi
anche con flag vecchi false/null, riuso da secondo utente e isolamento delle vecchie voci.
I test con MediaStream sintetico non sostituiscono la prova di fotocamera fisica iPhone.
