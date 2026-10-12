/** Human anatomy atlas: original, schematic illustrations, never an image-derived diagnosis.
 * The body template is educational, not the photographed person's internal anatomy.
 */
export type AtlasLayer = 'skin'|'muscles'|'nerves'|'organs'|'bones'|'reproductive';
export type AnatomyVariant = 'neutral'|'female'|'male';
export type AnatomyRegion = {
 id:string; label:string; detail:string; d:string; fill?:string; stroke?:string;
};
export const LAYERS:{key:AtlasLayer;label:string; color:string}[]=[
 {key:'skin',label:'Pelle',color:'#9be7f3'},
 {key:'muscles',label:'Muscoli',color:'#ef9277'},
 {key:'nerves',label:'Nervi',color:'#f6c97e'},
 {key:'organs',label:'Organi',color:'#dba3f6'},
 {key:'bones',label:'Ossa',color:'#d7ecf2'},
 {key:'reproductive',label:'Apparato riproduttivo',color:'#9fd9cf'}
];
const region=(id:string,label:string,detail:string,d:string):AnatomyRegion=>({id,label,detail,d});
const anatomy:Record<AtlasLayer,AnatomyRegion[]>={
 skin:[
 region('epidermis','Pelle del volto','L’epidermide protegge dall’ambiente esterno. Derma e tessuto sottocutaneo svolgono altre funzioni, tra cui sensibilità e termoregolazione.','M140 44 Q160 26 180 44 L181 80 Q176 102 160 109 Q144 102 139 82 Z'),
 region('torso_skin','Pelle del tronco','Una barriera protettiva che contribuisce alla regolazione della temperatura e ospita recettori sensoriali.','M124 132 Q160 110 195 132 L207 306 Q160 330 113 306 Z'),
 region('arm_skin','Pelle degli arti superiori','Protegge l’arto e partecipa alla percezione di pressione, temperatura e contatto.','M102 147 Q88 182 77 250 L57 388 Q54 407 69 410 L90 375 116 237 127 151 Z'),
 region('hand_skin','Cute della mano','Il palmo e i polpastrelli possiedono molti recettori per il tatto fine.','M56 386 L71 391 79 433 74 459 63 440 52 461 44 439 Z'),
 region('leg_skin','Pelle degli arti inferiori','Riveste le gambe e protegge i tessuti sottostanti.','M117 326 L155 337 154 477 149 554 132 567 120 477 104 392 Z')
 ],
 muscles:[
 region('pectorals','Muscoli pettorali','Contribuiscono ai movimenti delle braccia rispetto al tronco.','M121 149 Q146 134 159 157 Q143 194 118 185 Z M161 157 Q181 135 199 149 L202 186 Q174 194 161 157 Z'),
 region('abdominals','Muscoli addominali','Stabilizzano il tronco e contribuiscono alla flessione e al controllo della pressione addominale.','M135 204 Q160 213 185 204 L184 307 136 307 Z'),
 region('shoulder','Deltoidi','Consentono movimenti della spalla e partecipano all’elevazione dell’arto superiore.','M105 138 Q87 151 94 183 L122 207 133 148 Z M188 148 L205 138 Q232 151 228 183 L199 207 Z'),
 region('biceps','Bicipite brachiale','Partecipa alla flessione del gomito e alla supinazione dell’avambraccio.','M96 196 L119 212 106 287 88 273 Z M201 212 L224 196 234 273 216 287 Z'),
 region('forearm','Muscoli dell’avambraccio','Agiscono su polso e dita, consentendo movimenti e presa.','M86 290 L106 305 81 385 61 380 Z M215 305 L234 290 259 380 239 385 Z'),
 region('quadriceps','Quadricipite','Estende il ginocchio e contribuisce alla stabilità della gamba.','M115 345 Q133 335 154 349 L149 452 121 449 Z M166 349 Q185 335 205 345 L199 449 172 452 Z'),
 region('calves','Tricipite surale','Partecipa alla flessione plantare del piede, utile quando camminiamo o saliamo sulle punte.','M121 470 Q135 451 149 480 L145 545 132 549 Z M172 480 Q187 451 202 470 L189 549 176 545 Z')
 ],
 nerves:[
 region('brain','Encefalo','Riceve ed elabora informazioni, coordina funzioni motorie, sensoriali e autonome.','M137 47 Q141 27 160 30 Q183 27 187 47 L183 76 Q160 94 137 76 Z'),
 region('spinal','Midollo spinale','Trasmette segnali tra encefalo e corpo e coordina numerosi riflessi.','M155 101 L166 101 166 317 155 317 Z'),
 region('brachial','Plesso brachiale','Rete di nervi che porta segnali sensitivi e motori a spalla e arto superiore.','M154 126 Q124 136 107 165 L99 246 76 359 M166 126 Q196 136 213 165 L221 246 244 359'),
 region('radial','Nervo radiale (schema)','Partecipa al controllo di muscoli estensori del braccio e dell’avambraccio.','M115 166 Q95 218 102 273 L74 383 M205 166 Q225 218 218 273 L246 383'),
 region('sciatic','Nervo sciatico (schema)','Importante nervo dell’arto inferiore, si origina dal plesso sacrale e raggiunge i rami della gamba.','M150 302 Q129 340 128 410 L137 529 M170 302 Q191 340 192 410 L183 529')
 ],
 organs:[
 region('lungs','Polmoni','Consentono gli scambi tra ossigeno e anidride carbonica. Questo è un posizionamento schematico.','M130 153 Q143 137 152 161 L150 230 Q119 231 122 184 Z M168 161 Q181 137 194 153 L198 184 Q201 231 170 230 Z'),
 region('heart','Cuore','Pompa il sangue nella circolazione polmonare e sistemica.','M156 176 Q143 158 136 177 Q132 194 160 218 Q188 194 184 177 Q175 159 162 176 Z'),
 region('liver','Fegato','Interviene nel metabolismo, nella produzione di bile e nella trasformazione di molte sostanze.','M169 229 Q201 222 201 244 Q183 269 161 252 Z'),
 region('stomach','Stomaco','Mescola il cibo con i succhi gastrici e avvia parte della digestione.','M140 239 Q154 223 168 241 Q179 258 156 278 Q133 273 140 239 Z'),
 region('intestine','Intestino','Completa digestione e assorbimento di nutrienti e parte dell’acqua.','M135 281 Q160 268 184 281 L185 321 Q160 336 135 321 Z'),
 region('kidneys','Reni','Filtrano il sangue, regolano l’equilibrio idrosalino e producono urina.','M119 254 Q126 239 139 256 L136 281 Q118 285 119 254 Z M181 256 Q194 239 201 254 L201 281 Q183 285 181 256 Z'),
 region('bladder','Vescica urinaria','Raccoglie temporaneamente l’urina prima della minzione.','M149 329 Q160 320 171 329 L172 347 Q160 359 148 347 Z')
 ],
 bones:[
 region('skull','Cranio','Protegge l’encefalo e sostiene le strutture del volto.','M138 48 Q160 28 182 48 L183 82 171 98 149 98 137 82 Z'),
 region('spine','Colonna vertebrale','Sostiene il tronco e protegge il midollo spinale nel canale vertebrale.','M156 108 L164 108 168 309 153 309 Z'),
 region('ribs','Gabbia toracica','Protegge cuore e polmoni, partecipando alla meccanica respiratoria.','M123 156 Q160 133 197 156 L192 229 Q160 249 128 229 Z'),
 region('pelvis','Bacino osseo','Trasferisce il carico tra colonna e arti inferiori e protegge parte degli organi pelvici.','M121 301 Q160 317 199 301 L197 353 176 365 160 344 144 365 123 353 Z'),
 region('humerus','Omero','Osso del braccio tra spalla e gomito.','M109 172 L118 174 103 287 94 283 Z M202 174 L211 172 226 283 217 287 Z'),
 region('forearm_bones','Radio e ulna','Sono le due ossa dell’avambraccio; consentono, tra le altre cose, la pronazione e la supinazione.','M94 291 L103 297 74 400 66 395 Z M217 297 L226 291 254 395 246 400 Z'),
 region('femur','Femori','Ossa lunghe della coscia, collegano anca e ginocchio.','M134 357 L144 359 144 459 135 459 Z M176 359 L186 357 185 459 176 459 Z'),
 region('lower_leg','Tibia e fibula','Sostengono e stabilizzano la gamba tra ginocchio e caviglia.','M134 468 L144 468 142 555 136 555 Z M176 468 L186 468 184 555 178 555 Z')
 ],
 reproductive:[
 region('urinary_common','Vescica urinaria','Organo urinario, non riproduttivo, mostrato per orientamento anatomico.','M149 311 Q160 301 171 311 L172 332 Q160 345 148 332 Z')
 ]
};
export const reproductiveFemale:AnatomyRegion[]=[
 region('uterus','Utero (modello tipico)','Organo muscolare che può ospitare una gravidanza. Non è possibile sapere dalla foto se questa anatomia è presente.','M151 353 Q160 348 169 353 L166 384 155 384 Z'),
 region('ovaries','Ovaie (modello tipico)','Gonadi che producono ovociti e ormoni. La forma è semplificata.','M132 360 Q138 350 146 362 L140 375 Z M174 362 Q182 350 189 360 L181 375 Z'),
 region('vagina','Canale vaginale (schema)','Canale anatomico tra cervice uterina e regione vulvare nel modello selezionato.','M155 388 L166 388 164 411 157 411 Z'),
 region('vulva','Vulva (schema esterno)','Nome collettivo delle strutture genitali esterne tipiche del modello anatomico scelto.','M150 409 Q160 403 170 409 L164 427 156 427 Z')
];
export const reproductiveMale:AnatomyRegion[]=[
 region('testes','Testicoli (modello tipico)','Gonadi che producono spermatozoi e ormoni. La loro presenza non si può dedurre dall’aspetto.','M149 422 Q153 413 158 420 L158 435 150 438 Z M162 420 Q167 413 171 422 L169 438 161 435 Z'),
 region('prostate','Prostata (modello tipico)','Ghiandola situata sotto la vescica nella struttura anatomica qui illustrata.','M152 349 Q160 341 168 349 L165 361 155 361 Z'),
 region('ducts','Dotti deferenti (schema)','Parte delle vie genitali che trasportano gli spermatozoi.','M151 423 Q132 394 147 366 M169 423 Q188 394 173 366'),
 region('penis','Pene (schema esterno)','Organo genitale esterno tipico del modello selezionato, qui rappresentato schematicamente.','M155 369 L165 369 165 417 155 417 Z')
];
export function regionsFor(layer:AtlasLayer, variant:AnatomyVariant):AnatomyRegion[]{
 return layer==='reproductive' ? [...anatomy.reproductive,...(variant==='male'?reproductiveMale:variant==='female'?reproductiveFemale:[])] : anatomy[layer];
}
export const silhouettePath='M139 45 Q158 24 181 45 Q190 64 183 89 L174 101 174 116 Q215 119 225 149 L241 222 260 360 273 425 263 452 252 432 241 402 225 334 216 261 209 227 207 304 198 357 207 433 201 524 196 570 185 579 171 571 166 490 161 389 157 389 152 490 148 571 136 579 125 570 119 524 113 433 121 357 112 304 110 227 103 261 94 334 78 402 67 432 56 452 46 425 59 360 78 222 95 149 Q104 119 145 116 L145 101 136 89 Q131 64 139 45 Z';
