/** La giornata intera, rifatta adesso: la stessa pagina del punto del mattino. */
import { PaginaOra } from '@/src/components/pagine/PaginaOra';
import { PuntoDelMattino } from '@/src/components/brief/PuntoDelMattino';

export default function Giornata() {
  return (
    <PaginaOra titolo="La tua giornata" attiva="index" testID="pagina-giornata">
      <PuntoDelMattino fallback="Non riesco a leggere la giornata adesso. Riprova tra poco." />
    </PaginaOra>
  );
}
