/**
 * Vita — la superficie con cui si vede e si completa quello che ORA sa.
 *
 *     VITA E CONOSCIAMOCI NON SONO DUE PRODOTTI.
 *
 * La voce «Vita» della barra apriva `/contesti`, una schermata con un'altra
 * grammatica e un'altra idea di che cosa sia la vita di una persona; il
 * percorso approvato — «Conosciamoci» — viveva altrove, a `/life-setup`, e ci
 * si arrivava solo al primo accesso. Due esperienze concorrenti per la stessa
 * domanda: *che cosa sai di me, e che cosa ti manca?*
 *
 * Adesso la voce Vita apre questa, che è quella approvata. I dati di
 * `/contesti` non sono stati buttati: le situazioni in corso vivono qui sotto
 * «In questo periodo», e la rotta vecchia resta raggiungibile per chi ci
 * arriva da un link, ma non è più la destinazione di nessuna voce di menu.
 */
import { GuidedSetupScreen } from '@/src/life-setup/GuidedSetupScreen';

export default function Vita() {
  return <GuidedSetupScreen />;
}
