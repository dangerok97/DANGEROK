"""Public information for ORA's restricted personal banking evaluation."""
from html import escape
from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(include_in_schema=False)
CONTACT = 'francesconicolocefala@gmail.com'


def page(title: str, sections: list[tuple[str, str]]) -> HTMLResponse:
    content = ''.join(f'<section><h2>{escape(h)}</h2><p>{escape(p)}</p></section>' for h, p in sections)
    return HTMLResponse(f'''<!doctype html><html lang="it"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{escape(title)} — ORA</title>
<style>body{{margin:0;background:#f8f7f4;color:#192133;font:17px/1.65 system-ui,sans-serif}}main{{max-width:760px;margin:48px auto;padding:32px;background:white;border:1px solid #e3dfd8;border-radius:20px}}h1{{line-height:1.2}}h2{{font-size:21px;margin-top:30px}}a{{color:#205de5}}nav{{display:flex;gap:24px}}small{{color:#566174}}@media(max-width:800px){{main{{margin:12px;padding:22px}}}}</style></head>
<body><main><strong>ORA</strong><h1>{escape(title)}</h1><small>Progetto sperimentale a uso personale · Aggiornamento: 22 settembre 2026</small>
{content}<h2>Contatto</h2><p><a href="mailto:{CONTACT}">{CONTACT}</a></p>
<nav><a href="/privacy">Privacy</a><a href="/terms">Condizioni d’uso</a></nav></main></body></html>''', headers={'X-Content-Type-Options': 'nosniff', 'Referrer-Policy': 'no-referrer'})


@router.get('/privacy', response_class=HTMLResponse)
def privacy():
    return page('Privacy — collegamento bancario', [
        ('Ambito della sperimentazione', 'Questa pagina descrive il collegamento bancario di ORA per la sperimentazione personale limitata ai conti autorizzati. Non annuncia un servizio bancario aperto al pubblico e non costituisce l’informativa completa per una futura distribuzione pubblica di ORA.'),
        ('Dati e finalità', 'Quando il collegamento è configurato e autorizzato, ORA può ricevere informazioni sui conti, identificativi, saldi e movimenti resi disponibili dalla banca, oltre ai riferimenti tecnici della sessione e al suo stato. Questi dati servono a mostrare la situazione dei conti e a ricavare informazioni utili alla gestione personale, come spese ricorrenti e riepiloghi.'),
        ('Autorizzazione e credenziali', 'Il collegamento è facoltativo e passa attraverso Enable Banking e il percorso di autenticazione della banca. Le credenziali bancarie e i codici di conferma vanno inseriti soltanto nel percorso della banca: ORA non richiede di inserirli nella propria interfaccia. Il collegamento implementato è in sola lettura e non permette a ORA di disporre pagamenti.'),
        ('Infrastruttura e conservazione', 'Il backend e il database di ORA sono ospitati su Railway. Informazioni importate, riferimenti di collegamento e dati elaborati possono essere conservati nel database dell’applicazione. L’installazione attuale utilizza infrastruttura nella regione statunitense California. Non è ancora definito un termine automatico uniforme di cancellazione per tutti i dati della sperimentazione; per informazioni o richieste di cancellazione utilizzare il contatto riportato sotto.'),
        ('Revoca e richieste', 'È possibile gestire o revocare il consenso attraverso la banca e il portale consensi di Enable Banking, https://enablebanking.com/data-sharing-consents/. La revoca interrompe l’accesso futuro secondo le modalità del provider, ma non equivale automaticamente alla cancellazione dei dati già importati in ORA. Per richieste di accesso, correzione o cancellazione contattare il progetto via email.'),
        ('Limiti di questa pagina', 'La pubblicazione di questa pagina non certifica la conformità del progetto per l’apertura a utenti esterni. Prima di tale apertura saranno necessari l’identificazione del soggetto responsabile, un’informativa completa e la definizione delle condizioni e dei tempi di conservazione applicabili.'),
    ])


@router.get('/terms', response_class=HTMLResponse)
def terms():
    return page('Condizioni d’uso — sperimentazione personale', [
        ('Scopo', 'ORA è un progetto sperimentale di assistenza personale. Queste condizioni riguardano la prova del collegamento bancario sui propri conti autorizzati; non costituiscono un’offerta di servizio al pubblico.'),
        ('Collegamento dei conti', 'Collega esclusivamente conti per i quali sei autorizzato. L’accesso dipende dal consenso confermato presso la banca, dalla disponibilità dell’istituto presso Enable Banking e dall’abilitazione dell’applicazione. In modalità ristretta sono accessibili soltanto i conti preventivamente collegati all’applicazione del provider.'),
        ('Sola lettura', 'La funzione bancaria di ORA legge informazioni sui conti, saldi e movimenti. Non dispone bonifici o altri pagamenti. L’autorizzazione alla lettura non è un’autorizzazione a movimentare denaro.'),
        ('Aggiornamenti e affidabilità', 'I dati possono essere incompleti, non aggiornati o temporaneamente indisponibili. Il consenso può scadere e richiedere una nuova autorizzazione. Verifica importi e operazioni nell’app o nell’estratto conto della banca prima di assumere decisioni. I riepiloghi di ORA non costituiscono consulenza finanziaria.'),
        ('Interruzione e dati', 'Puoi interrompere l’uso e revocare il consenso presso la banca o Enable Banking. Per la gestione dei dati già importati consulta la pagina Privacy e scrivi al contatto indicato. Le funzionalità sperimentali possono cambiare o essere sospese; queste condizioni non limitano i diritti inderogabili applicabili.'),
    ])
