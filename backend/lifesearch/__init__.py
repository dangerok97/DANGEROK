"""
Cercare dentro una vita, non dentro un archivio.

    LA RICERCA E' UN'INTERFACCIA AL MODELLO DELLA VITA, NON UN TROVA-FILE.

Chi scrive «casa» non sta cercando un file che contiene la parola «casa».
Sta chiedendo: *cosa c'entra con la mia casa?* — l'acquisto in corso, i soldi
che ci girano intorno, il documento del mutuo, la mail del notaio. Sono cose
diverse fra loro, sono in posti diversi, e quello che le tiene insieme non e'
una parola: e' una relazione che qualcuno ha gia' stabilito.

Quattro moduli e un ordine.

  `index`     cosa contiene questa vita, in poche righe. E' quello che il
              modello guarda per capire di cosa si sta parlando: i nomi delle
              situazioni, quello che ORA sa, quali strumenti sono collegati.

  `interpret` una chiamata sola: cosa sta cercando questa persona, e a quali
              situazioni si riferisce. Nessun instradamento a parole chiave —
              «mutuo» non ha bisogno di stare in un elenco per portare alla
              casa.

  `resolve`   l'espansione, deterministica, nell'ordine che conta: prima le
              relazioni scritte, poi la provenienza, poi il giudizio, e per
              ultima la parola. Ogni risultato porta con se' *come* e' stato
              trovato, che serve a chi verifica e non si mostra a nessuno.

  `present`   i risultati raggruppati per significato, con la provenienza
              detta a parole e la storia rispettata: quello che e' stato
              superato non torna come corrente, e due verita' in conflitto
              restano due.
"""

from lifesearch.present import GROUPS
from lifesearch.search import search_a_life

__all__ = ["GROUPS", "search_a_life"]
