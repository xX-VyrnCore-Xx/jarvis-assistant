name: ui-ux-design
title: UI/UX design
domain: grafica
description: Progetta interfacce usabili: ricerca sugli utenti, flussi, wireframe, gerarchia, euristiche di usabilità, test e iterazione.
triggers: ux, ui, ui/ux, user experience, usabilità, progettare un'interfaccia, wireframe, flusso utente, user flow, design dell'app, schermata, interfaccia utente, test di usabilità, user research, persona utente

**Metodo**: 1) **capisci chi e perché**: obiettivo dell'utente, contesto, ostacoli (5 interviste valgono più di mille opinioni); 2) flussi: il percorso più breve per il compito principale, poi i casi di errore; 3) wireframe a bassa fedeltà prima dello stile; 4) gerarchia: una azione primaria per schermata, il resto secondario; 5) **euristiche di Nielsen**: stato del sistema visibile, linguaggio dell'utente, controllo e annullamento, coerenza, prevenzione errori, riconoscere anziché ricordare, flessibilità, design minimale, aiuto negli errori; 6) tutte le condizioni: vuoto, caricamento, errore, successo, offline; 7) test di usabilità con 5 persone su compiti reali, correggi, ripeti.
**Mobile**: bersagli di tocco ≥ 44-48 px, azioni principali raggiungibili col pollice, meno testo, tastiera giusta per il campo.
**Output**: flusso testuale, descrizione delle schermate con i componenti e gli stati, 3 problemi da risolvere per primi e come testarli.
@@@
name: design-system-e-ui-kit
title: Design system e componenti
domain: grafica
description: Crea un sistema di design coerente: token (colori, spaziature, tipografia), componenti riutilizzabili, varianti, tema chiaro/scuro e documentazione.
triggers: design system, ui kit, token di design, componenti riutilizzabili, libreria di componenti, variabili css, tema scuro, dark mode, storybook, tailwind config, coerenza grafica, stile dell'app, linee guida di stile

**Metodo**: 1) **token** semantici (non «blu-500» ma `--color-primary`, `--surface`, `--text-muted`): colore, tipografia (scala), spaziatura (scala a 4/8 px), raggi, ombre, durate; 2) tema chiaro/scuro ridefinendo i token, non i componenti; 3) componenti di base (bottone, campo, scheda, modale, tab, toast) con **stati** (normale, hover, focus visibile, attivo, disabilitato, errore, caricamento) e varianti limitate; 4) regole di composizione (griglia, margini, densità); 5) documentazione con esempi d'uso e «cosa non fare»; 6) accessibilità integrata (contrasto, focus, aree di tocco).
**Pratica**: parti dai componenti che usi davvero; poche varianti ben fatte; versiona e registra le modifiche.
**Output**: tabella dei token con valori, specifica dei componenti principali (stati e misure) e il codice CSS/Tailwind di partenza.
@@@
name: tipografia
title: Tipografia
domain: grafica
description: Sceglie e abbina font, definisce scale tipografiche, interlinea, lunghezza di riga e gerarchia per testi leggibili e di carattere.
triggers: tipografia, font, carattere tipografico, abbinare i font, scala tipografica, interlinea, leggibilità, serif, sans serif, google fonts, grassetto e corsivo, gerarchia del testo, dimensione del testo, kerning

**Metodo**: 1) il testo prima di tutto: leggibilità e tono; 2) **1-2 famiglie** al massimo (una per i titoli, una per il testo, oppure una sola con pesi diversi); per i web usa font di sistema o variabili con `font-display: swap`, solo i pesi necessari; 3) **scala** modulare (es. 1.25: 14/16/20/25/31/39 px); 4) testo corrente 16-18 px, **interlinea 1,4-1,6**, riga di **45-75 caratteri**, allineamento a sinistra, paragrafi con spazio; 5) gerarchia con dimensione, peso e colore (non solo grandezza); 6) contrasto adeguato e niente testo lungo in maiuscolo o su sfondi rumorosi; 7) abbinamenti: contrasto di struttura (serif + sans) e tono comune; evita font troppo simili.
**Output**: coppia di font con motivo, scala con valori in px/rem, snippet CSS, e le regole d'uso (titoli, testo, didascalie). Controlla le licenze dei font.
@@@
name: colore-e-palette
title: Colore, palette e contrasto
domain: grafica
description: Costruisce palette efficaci: teoria del colore, ruoli, contrasto WCAG, tema scuro, significato culturale e accessibilità per daltonici.
triggers: colori, palette, palette di colori, scegliere i colori, abbinare i colori, teoria del colore, contrasto, wcag, colore primario, sfumature, gradiente, daltonismo, hsl, hex, colore del brand, tema scuro colori

**Metodo**: 1) parti da 1 **colore guida** coerente con il tono del brand; 2) ruoli: primario (azioni), secondario/accento, neutri (sfondi e testi, 6-9 gradini), semantici (successo, avviso, errore, info); 3) schemi: monocromatico, analogo, complementare, triadico — in pratica 60% neutri, 30% primario, 10% accento; 4) genera le scale in spazi percettivi (HSL/OKLCH) con luminosità uniforme; 5) **contrasto WCAG**: testo normale ≥ 4,5:1, testo grande e componenti UI ≥ 3:1; 6) non affidare l'informazione al solo colore (icona, testo, forma); 7) **tema scuro**: non puro nero (#0d0b14, grigi scuri), saturazione ridotta, contrasto controllato; 8) verifica con simulatori di daltonismo.
**Output**: palette con codici (HEX/HSL) e ruolo di ciascuno, coppie testo/sfondo con il rapporto di contrasto calcolato (`calculate`), esempio di uso e variabili CSS.
@@@
name: layout-e-composizione
title: Layout, griglia e composizione
domain: grafica
description: Organizza gli elementi in una pagina o schermata: griglia, spaziatura, allineamento, prossimità, gerarchia visiva e ritmo.
triggers: layout, composizione, griglia, impaginazione, spaziatura, allineamento, gerarchia visiva, spazio bianco, margini, come disporre gli elementi, equilibrio visivo, struttura della pagina, responsive, mobile first, proporzioni

**Principi**: **prossimità** (ciò che è collegato sta vicino), **allineamento** (pochi assi netti), **contrasto** (dimensione, peso, colore per guidare l'occhio), **ripetizione** (coerenza), **spazio bianco** (respiro = chiarezza). Lo sguardo segue percorsi (F, Z): metti ciò che conta all'inizio.
**Metodo**: 1) contenuti in ordine di importanza; 2) griglia (12 colonne sul desktop, 4 sul mobile) con **spaziatura a multipli di 8 px**; 3) blocchi con spazio interno maggiore dello spazio fra gruppi correlati; 4) un solo punto focale per vista; 5) **responsive**: parti dal mobile, adatta ai breakpoint (≈ 640/768/1024/1280), flex/grid, unità relative, larghezza massima del testo; 6) allinea le immagini, tronca con criterio, controlla gli stati reali (testi lunghi, dati mancanti); 7) «strizza gli occhi»: la gerarchia resta chiara?
**Output**: schema ASCII del layout, misure (spaziature, colonne, breakpoint), snippet CSS grid/flex e un elenco dei difetti da evitare.
@@@
name: accessibilita-web
title: Accessibilità (WCAG, ARIA)
domain: grafica
description: Rende siti e app utilizzabili da tutti: WCAG, HTML semantico, tastiera, screen reader, ARIA, contrasto e test di accessibilità.
triggers: accessibilità, wcag, aria, screen reader, navigazione da tastiera, contrasto, testo alternativo, alt text, a11y, focus visibile, accessibile, lettore di schermo, norme di accessibilità, aria-label, accessibilità del sito

**Metodo (principi POUR: percepibile, utilizzabile, comprensibile, robusto)**: 1) **HTML semantico** prima di tutto (`button`, `a`, `nav`, `main`, `h1-h6` in ordine, `label` per ogni campo, tabelle vere); 2) **tastiera**: tutto raggiungibile con Tab nell'ordine logico, focus sempre visibile, nessuna trappola, scorciatoia «salta al contenuto»; 3) **alternative**: `alt` descrittivo (vuoto per le decorative), sottotitoli e trascrizioni; 4) **contrasto** 4,5:1 e niente informazioni solo a colore; 5) **ARIA** solo quando l'HTML non basta (`aria-label`, `aria-live` per aggiornamenti, ruoli e stati dei widget); regola: nessun ARIA è meglio di ARIA sbagliato; 6) testo ridimensionabile al 200%, bersagli di tocco ≥ 44 px, rispetto di `prefers-reduced-motion`; 7) messaggi di errore chiari e collegati ai campi.
**Test**: Lighthouse/axe + prova a mano con tastiera e uno screen reader (NVDA, VoiceOver, TalkBack).
**Output**: elenco dei problemi per gravità con correzione di codice; ricorda l'obbligo di legge per molti servizi (EAA/AgID in Italia).
@@@
name: logo-e-identita-visiva
title: Logo e identità visiva
domain: grafica
description: Progetta un logo e un sistema visivo: ricerca, concept, semplicità, versioni, colori, applicazioni e consegna dei file.
triggers: logo, disegnare un logo, marchio grafico, identità visiva, logotipo, monogramma, versioni del logo, brand kit, favicon, restyling del logo, manuale d'uso del marchio, simbolo del marchio

**Metodo**: 1) brief: cosa fa il brand, pubblico, valori, concorrenti (da cui differenziarsi); 2) concept: parole chiave → metafore → schizzi (tanti, a mano) → 3 direzioni; 3) un buon logo è **semplice, memorabile, distintivo, adattabile, senza tempo**; 4) **tipo**: simbolo, logotipo (solo testo), combinato; 5) funziona prima in **bianco e nero** e a 16 px; 6) versioni: principale, orizzontale/verticale, simbolo da solo, monocromatica, su fondo chiaro/scuro; **area di rispetto** e dimensione minima; 7) palette e font di supporto; 8) applicazioni (sito, social, biglietti, packaging) e verifica a diverse dimensioni.
**Consegna**: vettoriali (SVG/PDF/AI), PNG trasparenti, favicon e icona app, mini manuale d'uso.
**Output**: 3 concept descritti con razionale (forma, colore, font), indicazioni per realizzarli (anche come SVG) e checklist di verifica. Ricorda la verifica di unicità e la registrazione del marchio.
@@@
name: grafica-vettoriale-e-svg
title: Grafica vettoriale e SVG
domain: grafica
description: Crea e ottimizza grafica vettoriale: SVG a mano e con strumenti, path, viewBox, icone, animazioni, esportazione e uso sul web.
triggers: svg, vettoriale, grafica vettoriale, illustrator, inkscape, path svg, viewbox, icona svg, ottimizzare svg, svgo, disegnare in svg, animazione svg, vettorializzare, bezier

**Principi**: i vettori descrivono forme (non pixel): scalano senza perdere qualità, ideali per loghi, icone, illustrazioni piatte, grafici. Elementi base: `rect`, `circle`, `ellipse`, `line`, `polyline`, `polygon`, `path` (comandi `M L H V C S Q A Z`, maiuscolo = assoluto, minuscolo = relativo), `g` per i gruppi, `defs` per gradienti/clip/maschere.
**Pratica**: scegli un **`viewBox`** (es. `0 0 24 24`) e lavora a coordinate semplici; poche anchor point per curva (una curva pulita vale più di cento punti); `currentColor` per far ereditare il colore dal testo; tratti con `stroke-linecap/linejoin` coerenti e `vector-effect: non-scaling-stroke` se serve; converti i testi in tracciati solo nelle consegne; ottimizza con **SVGO**.
**Web**: inline (stile e animazioni con CSS), `<img>` (cache), sprite `<symbol>/<use>`; accessibilità (`role="img"` + `<title>`/`aria-label`, oppure `aria-hidden` se decorativo). Animazioni con CSS/SMIL, prestazioni solo su `transform`/`opacity`.
**Output**: codice SVG completo e commentato, pronto da incollare, con variante ottimizzata e uso in HTML.
@@@
name: css-e-animazioni
title: CSS avanzato e animazioni
domain: grafica
description: Realizza layout e animazioni con CSS moderno: flexbox, grid, variabili, container query, transizioni, keyframe e motion design performante.
triggers: css, flexbox, css grid, animazione css, transizione, keyframes, variabili css, container query, scss, tailwind, glassmorphism, hover effect, motion design, animare, scroll animation, sticky, clamp

**Layout**: **Grid** per strutture bidimensionali (`grid-template-columns: repeat(auto-fit, minmax(240px, 1fr))`), **Flexbox** per allineare in una dimensione (`gap`, `flex: 1 1 0`), `aspect-ratio`, `clamp()` per dimensioni fluide, unità `rem`/`dvh`, container query per componenti adattivi, `:has()` e `:is()`.
**Organizzazione**: variabili CSS per i token, specificità bassa (classi, BEM o utility), cascata con `@layer`, niente `!important`, mobile first con `min-width`.
**Animazioni**: transizioni per i cambi di stato (150-300 ms, `ease-out` in entrata), `@keyframes` per sequenze; anima solo **`transform` e `opacity`** (niente `width/top/left`), `will-change` con parsimonia, rispetta `prefers-reduced-motion`, il movimento deve avere uno scopo (guidare, dare riscontro, collegare stati). Scroll-driven animations e View Transitions dove supportate.
**Output**: codice HTML+CSS completo e funzionante, con i valori spiegati, il comportamento su mobile e un'avvertenza sul supporto dei browser quando serve.
@@@
name: fotografia-e-editing
title: Fotografia e post-produzione
domain: grafica
description: Migliora scatti e fotoritocco: esposizione, luce, composizione, messa a fuoco, colore, Lightroom/Photoshop e consigli con lo smartphone.
triggers: fotografia, foto, scattare, composizione fotografica, lightroom, photoshop, post-produzione, esposizione, iso, apertura, tempo di scatto, ritratto, paesaggio, raw, luce, ritocco, fotocamera, editing delle foto

**Esposizione**: triangolo **apertura–tempo–ISO**: apertura (f/) regola profondità di campo e luce, tempo congela o sfoca il movimento (regola: ≥ 1/focale per evitare il mosso), ISO sensibilità (più alto = più rumore). Modalità A/S per imparare; misurazione e compensazione per scene molto chiare o scure.
**Composizione**: regola dei terzi, linee guida, cornici naturali, primo piano/sfondo, spazio negativo, punto di vista basso o alto, **sfondo pulito**; la luce migliore è morbida (ora dorata, cielo velato), controluce per le silhouette.
**Smartphone**: pulisci l'obiettivo, tocca per mettere a fuoco ed esposizione, blocca AE/AF, usa la griglia, non lo zoom digitale.
**Editing (workflow)**: scatta in RAW → raddrizza e ritaglia → esposizione e contrasto → bilanciamento del bianco → alte luci/ombre → colore (vibranza prima di saturazione) → nitidezza e riduzione rumore con misura → ritocchi locali → esporta (sRGB, JPEG 85-90% per il web).
**Output**: consigli mirati, impostazioni di partenza e ordine delle modifiche; chiedi genere, luce e attrezzatura. Rispetta privacy e diritti d'immagine.
@@@
name: video-editing-e-motion
title: Montaggio video e motion graphics
domain: grafica
description: Realizza video: sceneggiatura, ripresa, montaggio, ritmo, audio, colore, sottotitoli, formati, codec ed esportazione per ogni piattaforma.
triggers: video, montaggio video, premiere, davinci resolve, final cut, after effects, motion graphics, sottotitoli, editing video, youtube, reel, codec, esportare il video, ffmpeg, formato video, ritmo del montaggio, tiktok video

**Metodo**: 1) obiettivo e pubblico → messaggio unico; 2) struttura: gancio nei primi 3 secondi → sviluppo → chiusura/CTA; 3) riprese: stabilità, luce, **audio pulito** (il pubblico perdona la qualità video, non l'audio cattivo), coperture (piano largo, medio, dettagli); 4) montaggio: taglia tutto ciò che non serve, ritmo con stacchi sul movimento/sulla musica, J-cut/L-cut per fluidità, transizioni sobrie, B-roll per coprire; 5) audio: voce chiara, musica sotto la voce (−18/−20 dB), normalizza; 6) colore: correzione prima della stilizzazione; 7) sottotitoli (molti guardano senza audio) e grafiche leggibili; 8) **export**: H.264/AAC MP4, 16:9 (1080p) per YouTube, 9:16 per Reel/TikTok/Shorts, bitrate adeguato.
**ffmpeg utile**: `ffmpeg -i in.mov -c:v libx264 -crf 20 -c:a aac out.mp4`.
**Output**: scaletta/script con tempi, lista riprese, impostazioni di esportazione; musica e immagini con licenza corretta.
@@@
name: grafica-3d-e-blender
title: Grafica 3D e Blender
domain: grafica
description: Modellazione, texture, illuminazione e render 3D con Blender: flusso di lavoro, topologia, materiali PBR, ottimizzazione ed esportazione.
triggers: 3d, blender, modellazione 3d, render, texture, materiali pbr, mesh, uv map, topologia, animazione 3d, rigging, glb, gltf, cycles, eevee, scultura 3d, low poly

**Flusso**: 1) riferimenti e blockout con forme semplici (proporzioni prima dei dettagli); 2) modellazione con **topologia pulita** (quad, anelli di spigoli dove si deforma, pochi triangoli/n-gon), modificatori (Subdivision, Mirror, Bevel) non distruttivi; 3) **UV unwrap** con tagli nascosti e densità di texel uniforme; 4) materiali **PBR** (base color, roughness, metallic, normal) dipinti o procedurali; 5) luci: tre punti (principale, riempimento, controluce) o HDRI, esposizione e «Filmic/AgX»; 6) render: Eevee per velocità, Cycles per realismo (denoise, campioni adeguati); 7) post-processo di composizione.
**Per web, app e giochi**: poligoni contenuti, texture potenza di 2 e compresse, **glTF/GLB** come formato, LOD, baking di luci e normali.
**Animazione**: keyframe, curve nel Graph Editor, rig con ossa e pesi.
**Output**: passi in ordine con scorciatoie e impostazioni, e i controlli di qualità prima dell'export; chiedi lo scopo finale (render, gioco, web).
@@@
name: figma-e-prototipi
title: Figma, prototipi e consegna agli sviluppatori
domain: grafica
description: Lavora bene con Figma: auto layout, componenti e varianti, stili e variabili, prototipi interattivi e handoff pulito allo sviluppo.
triggers: figma, prototipo, prototipazione, auto layout, componenti figma, varianti, handoff, dev mode, mockup, design in figma, adobe xd, sketch, wireframe digitale, libreria figma

**Metodo**: 1) struttura il file in pagine (Bozze, Componenti, Schermate, Archivio) con nomi chiari e livelli ordinati; 2) **Auto layout** su tutto (spaziature e padding coerenti, ridimensionamento che si comporta come il codice), vincoli per il responsive; 3) **componenti** con **varianti** e proprietà (stato, dimensione, icona on/off); 4) **stili e variabili** per colori, tipografia, spaziature, tema chiaro/scuro; 5) prototipo: collega i flussi principali, interazioni (tocco, trascina, smart animate) con micro-transizioni sobrie; 6) test del prototipo con utenti reali; 7) **handoff**: Dev Mode, annotazioni su comportamenti e stati (vuoto, errore, caricamento), asset esportati (SVG/PNG @1x-@3x), nomi coerenti con il codice, changelog.
**Output**: struttura del file, elenco di componenti e varianti da creare, regole di nomenclatura e checklist di consegna.
@@@
name: grafica-per-stampa
title: Grafica per la stampa
domain: grafica
description: Prepara file per la stampa: CMYK, risoluzione, abbondanza, margini di sicurezza, profili colore, font, formati di consegna e carte.
triggers: stampa, tipografia stampa, cmyk, abbondanza, margine di sicurezza, 300 dpi, file per la stampa, biglietti da visita, volantino, brochure, pdf per la stampa, profilo colore, pantone, packaging, stampare

**Regole**: lavora fin dall'inizio nelle dimensioni finali con **abbondanza (bleed) 3 mm** per lato, **margine di sicurezza interno 3-5 mm** per testi e loghi; immagini a **300 ppi** alla dimensione finale (non ingrandire dopo); colore **CMYK** (profilo indicato dalla tipografia, es. FOGRA39/FOGRA51) o colori **Pantone/spot** per tinte esatte; **nero ricco** solo per grandi aree, testo piccolo in K100; **incorpora o converti in tracciati i font**; tracciati e linee ≥ 0,25 pt; limita la copertura totale d'inchiostro (≈ 300%).
**Consegna**: PDF/X-1a o PDF/X-4 con segni di taglio e abbondanza, controllo preflight, richiesta di una **prova colore**; per i colori fedeli ricorda che lo schermo (RGB) non coincide con la stampa.
**Carte e finiture**: patinata lucida/opaca, uso-mano, grammatura (170-350 g), plastificazione, vernice UV, fustella.
**Output**: checklist specifica per il prodotto (formato, margini, risoluzione, colore) e impostazioni di esportazione; consiglia di verificare le specifiche della tipografia scelta.
@@@
name: data-visualization
title: Visualizzazione dei dati
domain: grafica
description: Sceglie e disegna grafici efficaci: tipo giusto, scale, colori, etichette, dashboard e storie con i dati senza ingannare.
triggers: grafico, grafici, visualizzazione dei dati, data visualization, dashboard, chart, istogramma, grafico a barre, grafico a linee, d3, chart.js, matplotlib, infografica, mappa di calore, rappresentare i dati, tabella o grafico

**Metodo**: 1) **domanda e messaggio**: cosa deve capire chi guarda? 2) scegli la forma: confronto → **barre**; andamento nel tempo → **linee**; distribuzione → istogramma/box plot; relazione → dispersione; parti di un tutto (poche) → barre impilate o torta a 2-4 fette; ranking → barre ordinate; geografia → mappe coropletiche/a punti; molti numeri esatti → tabella; 3) **non ingannare**: asse delle barre da zero, scale coerenti, niente 3D, niente doppi assi ambigui; 4) **meno inchiostro**: togli griglie pesanti, bordi, legende ridondanti, etichetta direttamente le serie; 5) colore con scopo: un colore per evidenziare, il resto grigio; palette sequenziali/divergenti corrette, daltonici-friendly; 6) titolo che dice la **conclusione**, sottotitolo con unità e periodo, fonte; 7) dashboard: KPI principali in alto, poche viste, filtri chiari, mobile.
**Output**: tipo di grafico consigliato con motivo, specifica (assi, colori, etichette) e codice (matplotlib/Chart.js/D3/SVG) pronto.
@@@
name: immagini-con-ai
title: Immagini generate con l'AI
domain: grafica
description: Genera e rifinisce immagini con modelli di AI: prompt efficaci, stile e coerenza, ritocchi, upscale, limiti, diritti e uso responsabile.
triggers: immagine ai, generare immagini, midjourney, stable diffusion, dall-e, prompt per immagini, ai art, controlnet, lora, upscale, inpainting, flux, immagini generate, illustrazione con ai, text to image, sfondo con ai

**Metodo**: 1) obiettivo (uso, formato, tono) e riferimenti; 2) **prompt** a strati: soggetto → azione/posa → ambiente → stile (fotografia, illustrazione, acquerello, 3D) → inquadratura/lente → luce → atmosfera/colori → qualità; frasi concrete, niente elenchi caotici; **prompt negativo** dove supportato; 3) iterazione: cambia una cosa alla volta, fissa il seed per confronti, usa riferimenti di stile/immagine; 4) strumenti di controllo: img2img, inpainting (correggi mani, testi, dettagli), ControlNet/riferimenti di posa, LoRA per coerenza di stile o personaggio; 5) post-produzione: upscale, correzione colore, ritocchi, testo aggiunto a parte (i modelli sbagliano spesso le scritte); 6) controlli: anatomia, artefatti, coerenza.
**Diritti e responsabilità**: leggi le licenze d'uso del servizio, evita stili e marchi protetti per copia, niente persone reali in contesti ingannevoli (deepfake), dichiara l'uso dell'AI quando richiesto.
**Output**: 3 prompt completi (con parametri indicativi) e consigli di rifinitura.
@@@
name: icone-e-app-icon
title: Icone e icona dell'app
domain: grafica
description: Progetta icone e icone di app: stile coerente, griglia, icone adattive Android, formati iOS/Windows/favicon e checklist di esportazione.
triggers: icona, icona dell'app, app icon, icone, icon pack, favicon, icona adattiva, adaptive icon, icona android, icona windows, ico, icns, pittogramma, set di icone, icona del sito

**Principi**: forma **semplice e riconoscibile anche a 16-48 px**, un solo concetto, contrasto forte con lo sfondo, niente testo piccolo né dettagli sottili, stile coerente (stesso spessore del tratto, angoli, riempimento). Prova su sfondi chiari/scuri e in bianco e nero.
**Icone UI**: griglia 24×24 (area viva 20×20), tratto 1,5-2 px, estremi arrotondati coerenti, un solo set (Lucide/Material/Phosphor) invece di mescolare.
**Icona app**: **Android adattiva** = primo piano + sfondo 108×108 dp con **zona di sicurezza 66×66 dp** al centro (la maschera può essere cerchio, squircle, goccia) + versione monocromatica per «icone a tema»; Play Store 512×512 PNG. **iOS**: 1024×1024 senza trasparenza né angoli (li arrotonda il sistema). **Windows**: `.ico` multi-risoluzione (16, 32, 48, 256) e riquadri; **Tauri** genera tutto da un PNG 1024 con `tauri icon`; Capacitor con `@capacitor/assets`. **Web**: favicon SVG + 32/180/192/512 PNG + `manifest`.
**Output**: concept (forma, colori, metafora), specifica di esportazione con tutte le misure e, se utile, l'SVG dell'icona.
