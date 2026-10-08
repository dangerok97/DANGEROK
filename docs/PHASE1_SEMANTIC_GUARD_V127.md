# ORA v127: controllo semantico di Fase 1

Il nuovo controllo distingue le letture HTTP valide dalla correttezza della risposta finale. Prima della pubblicazione, il loop sostituisce raccomandazioni sul traffico non basate su confronti tra orari di partenza. Il runner di test verifica la durata stimata e le osservazioni meteo, senza considerare una risposta del provider sufficiente per il successo del collaudo.

Il risultato tecnico e quello del controllo testuale sono riportati separatamente. Il controllo è limitato allo scenario percorso/meteo e non sostituisce una revisione umana generale. I test di simulazione non dimostrano la qualità del modello reale. La Fase 1 e l'autonomia generale restano aperte.
