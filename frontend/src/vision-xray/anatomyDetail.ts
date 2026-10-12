/** Additional educational landmarks. Front-projection schematics, not patient imaging. */
import type {AnatomyRegion, AtlasLayer} from './anatomyAtlas';
const part=(id:string,label:string,detail:string,d:string):AnatomyRegion=>({id,label,detail,d});
export const ANATOMY_DETAIL:Partial<Record<AtlasLayer,AnatomyRegion[]>>={
 bones:[
 part('clavicles','Clavicole','Collegano lo sterno alle scapole e mantengono la spalla distanziata dal torace.','M158 139 Q136 135 112 148 L109 154 Q134 145 158 147 Z M162 139 Q184 135 208 148 L211 154 Q186 145 162 147 Z'),
 part('sternum','Sterno','Osso piatto anteriore del torace, articolato con le cartilagini costali.','M155 148 L165 148 L168 220 152 220 Z'),
 part('mandible','Mandibola','Osso mobile della mascella inferiore; sostiene i denti inferiori e partecipa alla masticazione.','M140 78 Q158 107 180 78 L174 93 161 102 147 93 Z'),
 part('patella','Rotule','Ossa sesamoidi davanti al ginocchio: migliorano la leva del quadricipite.','M127 446 Q135 438 144 446 L142 463 130 463 Z M175 446 Q184 438 193 446 L190 463 177 463 Z'),
 part('scapula','Scapole (proiezione)','Ossa piatte posteriori della cintura scapolare: qui sono solo indicate nella proiezione frontale.','M120 155 L145 177 129 217 Z M200 155 L175 177 191 217 Z')
 ],
 muscles:[
 part('trapezius','Trapezio','Muscolo superficiale posteriore che mobilizza e stabilizza la scapola. Il disegno frontale è simbolico.','M152 111 L109 141 137 165 160 125 Z M168 111 L211 141 183 165 160 125 Z'),
 part('serratus','Dentato anteriore','Stabilizza la scapola sul torace ed è importante nell’elevazione del braccio.','M120 197 L138 202 132 228 117 220 Z M182 202 L200 197 203 220 188 228 Z'),
 part('obliques','Obliqui addominali','Contribuiscono a rotazione, flessione laterale e stabilizzazione del tronco.','M117 217 L135 221 139 293 119 303 Z M185 221 L203 217 201 303 181 293 Z'),
 part('sternocleidomastoid','Sternocleidomastoideo','Muscolo del collo che contribuisce a rotazione e flessione del capo.','M143 93 L155 94 162 139 155 143 Z M177 93 L165 94 158 139 165 143 Z'),
 part('tibialis','Tibiale anteriore','Contribuisce alla dorsiflessione della caviglia e al controllo del piede durante il passo.','M126 480 L134 477 140 550 132 551 Z M186 480 L194 477 188 551 180 550 Z')
 ],
 nerves:[
 part('trigeminal','Nervo trigemino (V)','Principale sensibilità del volto; alcuni rami controllano i muscoli masticatori.','M154 67 Q143 66 139 73 M154 68 Q143 78 145 89 M166 67 Q178 66 181 73 M166 68 Q177 78 175 89'),
 part('vagus','Nervo vago (X)','Nervo cranico con importanti connessioni parasimpatiche a torace e addome; decorso molto semplificato.','M155 83 Q146 124 149 163 Q142 201 149 256 M165 83 Q174 124 171 163 Q178 201 171 256'),
 part('femoral_nerve','Nervo femorale','Innerva fra gli altri diversi muscoli anteriori della coscia e trasporta sensibilità da aree dell’arto inferiore.','M155 307 Q135 340 133 386 L136 451 M165 307 Q185 340 187 386 L184 451'),
 part('ulnar_nerve','Nervo ulnare','Importante per parte della muscolatura intrinseca della mano e per la sensibilità di mignolo e lato ulnare dell’anulare.','M109 175 Q102 251 90 296 L61 400 M211 175 Q218 251 230 296 L259 400')
 ],
 organs:[
 part('trachea','Trachea','Condotto respiratorio sostenuto da anelli cartilaginei che si divide nei bronchi principali.','M155 113 L165 113 165 161 Q178 172 184 184 L179 190 Q168 174 160 169 Q152 174 141 190 L136 184 Q142 172 155 161 Z'),
 part('diaphragm','Diaframma','Muscolo respiratorio a cupola che separa cavità toracica e addominale.','M122 227 Q157 201 198 227 L195 239 Q159 217 125 239 Z'),
 part('pancreas','Pancreas','Produce enzimi digestivi e ormoni come insulina e glucagone. È prevalentemente retroperitoneale.','M140 261 Q159 254 181 261 L180 270 Q160 266 143 274 Z'),
 part('spleen','Milza','Organo linfoide che filtra il sangue e partecipa alla risposta immunitaria.','M118 240 Q131 235 135 253 Q131 270 120 265 Z'),
 part('esophagus','Esofago','Trasporta il bolo alimentare dalla faringe allo stomaco attraverso la peristalsi.','M153 105 L159 105 Q161 166 157 221 Q150 232 148 244 L143 241 Q151 216 151 185 Z'),
 part('large_intestine','Intestino crasso','Assorbe acqua ed elettroliti e trasporta il contenuto verso il retto. Lo schema non mostra tutti i tratti anatomici.','M133 279 L145 277 142 313 Q160 329 180 314 L178 277 190 279 191 322 Q160 350 130 324 Z'),
 part('small_intestine','Intestino tenue','Sede principale dell’assorbimento dei nutrienti: comprende duodeno, digiuno e ileo.','M145 283 Q169 278 178 293 Q145 295 179 304 Q146 312 174 319 Q152 328 144 312 Z')
 ]
};
