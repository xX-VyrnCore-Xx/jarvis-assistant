name: hardware-e-pc
title: Hardware, PC e componenti
domain: tecnologia
description: Sceglie, assembla, aggiorna e diagnostica PC e componenti: CPU, GPU, RAM, SSD, alimentatore, raffreddamento, compatibilità e guasti.
triggers: pc, computer, hardware, assemblare un pc, scheda video, gpu, cpu, processore, ram, ssd, alimentatore, scheda madre, upgrade del pc, il pc è lento, temperature, surriscaldamento, pc da gaming, portatile, compatibilità componenti

**Metodo (scelta/upgrade)**: 1) uso e budget (ufficio, gaming, montaggio, sviluppo, AI); 2) il **collo di bottiglia** decide dove spendere: gaming → GPU; compilazione/rendering → CPU e core; molte schede/VM → RAM (16 GB base, 32 GB comodi); caricamenti lenti → **SSD NVMe**; 3) compatibilità: socket e chipset ↔ CPU, tipo di RAM (DDR4/DDR5), formato scheda madre/case, lunghezza GPU, **alimentatore** di qualità con margine (≈ 20-30% oltre il consumo stimato) e connettori giusti; 4) raffreddamento adeguato, flusso d'aria davanti→dietro; 5) controlla prezzi e recensioni **attuali**.
**Diagnosi «PC lento/instabile»**: temperature e polvere, spazio libero su disco, processi (Task Manager), salute dell'SSD (SMART), aggiornamenti di driver/BIOS, test RAM (MemTest86), sostituzione di un componente alla volta.
**Output**: lista componenti con motivazione e compatibilità verificata, oppure albero di diagnosi in ordine di costo/rischio. Spegni e scollega prima di toccare l'interno; antistatico.
@@@
name: reti-e-wifi
title: Reti, Wi-Fi e connessione
domain: tecnologia
description: Risolve e configura reti domestiche e piccoli uffici: Wi-Fi lento, router, DNS, VPN, IP, porte, mesh e diagnosi della connessione.
triggers: rete, wifi, wi-fi, router, internet lento, connessione lenta, dns, vpn, ip, porta, port forwarding, mesh, ripetitore, ping, modem, fibra, lan, segnale wifi debole, rete domestica

**Metodo di diagnosi (dal vicino al lontano)**: 1) è un solo dispositivo o tutti? 2) cavo vs Wi-Fi (il cavo isola il problema); 3) riavvia modem/router; 4) `ping 8.8.8.8` (rete ok?) poi `ping google.com` (DNS ok? se no, cambia DNS: 1.1.1.1/9.9.9.9); 5) `traceroute`/`tracert` per vedere dove si ferma; 6) test di velocità sul cavo vs operatore.
**Wi-Fi**: posizione centrale e alta, lontano da ostacoli; 5 GHz (veloce, corto raggio) e 2,4 GHz (lungo raggio, più disturbi), 6 GHz con Wi-Fi 6E/7; canali meno affollati; **mesh** o access point cablati meglio dei ripetitori; WPA3/WPA2, password lunga, WPS spento, firmware aggiornato, rete ospiti separata per IoT.
**Servizi**: IP riservato (DHCP) + port forwarding solo se indispensabile (meglio VPN o tunnel); VPN per reti pubbliche (non per anonimato magico).
**Output**: passaggi numerati con comandi e cosa aspettarsi, e quando contattare l'operatore.
@@@
name: privacy-e-sicurezza-personale
title: Privacy e sicurezza personale online
domain: tecnologia
description: Protegge account, dispositivi e dati: password manager, autenticazione a due fattori, phishing, backup, aggiornamenti, truffe e impostazioni di privacy.
triggers: password, password manager, 2fa, autenticazione a due fattori, phishing, truffa, account hackerato, sicurezza online, privacy, antivirus, truffe online, spid sicuro, passkey, vpn privacy, ransomware, rubata l'identità, sicurezza dello smartphone

**Priorità (in ordine di efficacia)**: 1) **password manager** + password uniche e lunghe (frasi); 2) **2FA** su email, banca, cloud e social (app o chiave, meglio di SMS) e **passkey** dove disponibili; 3) **aggiornamenti** automatici di sistema e app; 4) **backup** (regola 3-2-1); 5) attenzione a link e allegati: controlla mittente, dominio reale, urgenza sospetta; nessuna banca chiede codici o password per telefono/SMS; 6) privacy: permessi delle app, tracciamento pubblicitario, account social, ricerca di data breach (haveibeenpwned); 7) blocco schermo e cifratura del dispositivo, «trova il mio dispositivo».
**Se sei stato truffato/hackerato**: cambia subito la password dell'email, attiva 2FA, disconnetti le sessioni, avvisa banca e blocca carte, controlla inoltro automatico email, denuncia alla Polizia Postale (e al Garante se riguarda dati personali).
**Output**: checklist personalizzata in ordine di priorità, spiegazioni semplici, nessun allarmismo. Non chiedere mai password o codici all'utente.
@@@
name: smartphone-e-app
title: Smartphone, app e impostazioni
domain: tecnologia
description: Aiuta con Android e iPhone: scelta, impostazioni, batteria, spazio, privacy, trasferimento dati, problemi comuni e app utili.
triggers: smartphone, telefono, android, iphone, ios, batteria che dura poco, spazio pieno, app, impostazioni del telefono, trasferire i dati, nuovo telefono, telefono lento, aggiornamento android, scegliere uno smartphone, notifiche

**Batteria**: luminosità adattiva, aggiornamenti, ottimizzazione per app in background (Impostazioni → Batteria), disattiva localizzazione/Bluetooth/Wi-Fi inutilizzati, individua le app che consumano, niente «task killer»; batteria al 20-80% quando possibile; sostituzione se la salute è < 80%.
**Spazio**: foto/video su cloud + «libera spazio», cache e file scaricati, app non usate, download offline di streaming.
**Lentezza**: riavvia, aggiorna sistema e app, svuota spazio, controlla le app in avvio, ripristino di fabbrica come ultima risorsa (dopo backup).
**Privacy**: permessi (posizione «solo con l'app in uso», microfono/fotocamera), ID pubblicitario, app da fonti ufficiali.
**Scegliere**: budget → priorità (fotocamera, batteria, anni di aggiornamenti garantiti, schermo, ecosistema); verifica recensioni e prezzi attuali.
**Nuovo telefono**: backup, strumento di trasferimento, 2FA/chiavi da trasferire **prima**, eSIM/SIM.
**Output**: passi con il percorso del menu (specifica Android/iOS e versione se serve).
@@@
name: smart-home-e-iot
title: Casa intelligente e IoT
domain: tecnologia
description: Progetta una smart home affidabile: standard (Matter, Zigbee, Z-Wave, Wi-Fi), hub, Home Assistant, automazioni, sicurezza e privacy.
triggers: smart home, domotica, home assistant, matter, zigbee, z-wave, iot, luci smart, sensori, termostato smart, alexa, google home, homekit, automazione domestica, presa smart, tasmota, esphome

**Metodo**: 1) cosa vuoi ottenere (comfort, risparmio, sicurezza) e quali automazioni valgono davvero; 2) scegli lo standard: **Matter/Thread** (interoperabile, locale), **Zigbee/Z-Wave** (affidabili, a basso consumo, serve hub/coordinatore), Wi-Fi (semplice ma pesa sulla rete e dipende dal cloud); 3) **controllo locale** prima del cloud (funziona anche senza internet): **Home Assistant** su Raspberry Pi/mini PC o NAS; 4) rete: SSID/VLAN dedicata agli IoT, segnale Wi-Fi 2,4 GHz stabile; 5) automazioni semplici e prevedibili (se-allora con condizioni e orari), sempre un **interruttore manuale** e un fallback; 6) sicurezza: password uniche, aggiornamenti, niente apertura di porte, backup della configurazione; 7) privacy: attenzione a microfoni/telecamere, dati nel cloud.
**Output**: architettura (hub, protocolli, dispositivi consigliati per categoria), 5 automazioni utili con la logica, e passi di installazione. Verifica compatibilità e prezzi aggiornati.
@@@
name: windows-macos-supporto
title: Supporto Windows, macOS e Linux
domain: tecnologia
description: Risolve problemi quotidiani dei sistemi operativi: avvio, aggiornamenti, driver, spazio, prestazioni, errori, ripristino e scorciatoie.
triggers: windows, windows 11, macos, mac, blue screen, schermata blu, errore di windows, ripristino, driver, il computer non si avvia, aggiornamento di windows, formattare, installare windows, spazio su disco, task manager, powershell, avvio lento

**Metodo di diagnosi**: 1) messaggio/codice d'errore esatto e cosa è cambiato di recente (aggiornamento, driver, programma); 2) soluzioni dalla meno alla più invasiva: riavvio → modalità provvisoria → ripristino configurazione/punto di ripristino → disinstalla l'ultimo aggiornamento/driver → controllo file (`sfc /scannow`, `DISM /Online /Cleanup-Image /RestoreHealth`) → controllo disco (`chkdsk`, SMART) → ripristino/reinstallazione (dopo backup); 3) per le prestazioni: app in avvio, spazio libero (≥ 15%), malware, temperature, driver GPU/chipset.
**macOS**: Utility Disco, modalità di ripristino, azzera NVRAM (Intel), Monitoraggio Attività.
**Installazione pulita**: backup, chiavetta di installazione ufficiale, driver dal produttore, aggiornamenti, programmi.
**Output**: passi numerati con comandi esatti e cosa verificare dopo; **avvisa prima di operazioni che cancellano dati** e proponi il backup. Con il PC collegato posso usare gli strumenti `pc_*` solo con il consenso.
@@@
name: linux-e-self-hosting
title: Linux, home server e self-hosting
domain: tecnologia
description: Monta un home server o NAS e ospita servizi in proprio (Docker, reverse proxy, backup, accesso remoto) in modo sicuro e manutenibile.
triggers: self hosting, self-hosting, home server, nas, raspberry pi, docker compose, nextcloud, plex, jellyfin, pi-hole, reverse proxy, nginx, caddy, traefik, tailscale, wireguard, ubuntu server, proxmox, server a casa

**Metodo**: 1) cosa vuoi ospitare (file, foto, media, DNS/ad-block, domotica, repository) e quanto è critico; 2) hardware: mini PC a basso consumo/Raspberry Pi 4-5 per iniziare, **SSD** (e dischi NAS CMR) per i dati, UPS se i dati contano; 3) sistema: Debian/Ubuntu Server, aggiornamenti automatici di sicurezza, utente non root, SSH con chiavi, firewall (`ufw`); 4) servizi in **Docker Compose** (un file per servizio, volumi con nome, versioni fissate), reverse proxy (Caddy semplice con HTTPS automatico) e certificati; 5) **accesso remoto**: VPN (Tailscale/WireGuard) invece di aprire porte; 6) **backup 3-2-1** testando il ripristino; 7) monitoraggio base (Uptime Kuma, SMART, spazio).
**Attenzione**: il self-hosting richiede manutenzione; non esporre servizi senza autenticazione; rispetta le licenze dei contenuti.
**Output**: architettura, `docker-compose.yml` di esempio commentato, comandi di installazione e checklist di sicurezza e backup.
@@@
name: elettronica-arduino-raspberry
title: Elettronica, Arduino e Raspberry Pi
domain: tecnologia
description: Progetti di elettronica per maker: microcontrollori (Arduino, ESP32, Pico), sensori, circuiti base, Raspberry Pi, sicurezza e debug.
triggers: arduino, esp32, raspberry pi, raspberry pi pico, microcontrollore, sensore, led, resistenza, breadboard, circuito, elettronica, gpio, saldare, multimetro, micropython, platformio, relè, servo, i2c

**Metodo**: 1) obiettivo e sensori/attuatori necessari; 2) scegli la scheda: **Arduino** (semplice), **ESP32** (Wi-Fi/Bluetooth, economico), **Pico** (MicroPython/C), **Raspberry Pi** (computer Linux completo); 3) elettronica base: **legge di Ohm** V = I·R, resistenza per un LED R = (Vcc − Vled)/I (es. (5−2)/0,02 = 150 Ω); tensioni logiche (3,3 V vs 5 V: non collegare 5 V a pin a 3,3 V), massa comune, **condensatori di disaccoppiamento**, resistenze di pull-up/pull-down, **diodo di ricircolo** sui carichi induttivi, transistor/MOSFET o relè per carichi alti (mai pilotarli direttamente dal pin); 4) bus: I²C (2 fili, indirizzi), SPI, UART; 5) software: struttura `setup()/loop()`, **niente `delay()` bloccanti** (usa `millis()`), antirimbalzo dei pulsanti, lettura analogica con media; 6) debug: multimetro, seriale, cambia una cosa alla volta.
**Sicurezza**: tensione di rete (230 V) solo con competenza e componenti certificati; batterie LiPo con protezioni.
**Output**: schema a parole/ASCII, elenco componenti con valori, codice commentato e prove di verifica.
@@@
name: intelligenza-artificiale-per-tutti
title: Usare bene l'intelligenza artificiale
domain: tecnologia
description: Spiega l'AI generativa e come sfruttarla: casi d'uso, limiti (allucinazioni, bias), verifica, privacy, strumenti e scelta del modello giusto.
triggers: intelligenza artificiale, chatgpt, gemini, claude, ai generativa, come usare l'ai, allucinazioni, copilot, modello linguistico, llm per principianti, ai per il lavoro, privacy e ai, quale ai scegliere, deepseek, ollama, ai locale

**Cos'è**: i modelli linguistici predicono testo plausibile da enormi quantità di dati: ottimi per bozze, sintesi, riscritture, traduzioni, spiegazioni, idee, codice, estrazione di dati; **non sono fonti di verità** e possono inventare (allucinazioni), anche con tono sicuro.
**Come usarli bene**: contesto e obiettivo chiari, esempi, formato richiesto, dati reali incollati (non a memoria), richiesta di ragionare per passi, controlla numeri e fonti, itera; chiedi «cosa non sai/cosa verificare»; per ricerche usa strumenti con fonti.
**Limiti e rischi**: bias, date oltre la conoscenza del modello, matematica non verificata (usa un calcolatore), **privacy** (non incollare dati sensibili in servizi che li conservano; valuta opzioni locali come Ollama per dati riservati), copyright e uso responsabile.
**Scelta**: compito → modello (veloce/economico per attività semplici, più capace per ragionamento e codice complesso), costi, limiti di contesto, politica dati.
**Output**: spiegazione semplice con esempi concreti dell'utente, 3 prompt pronti e una lista di cosa verificare sempre.
@@@
name: prompt-engineering
title: Scrivere buoni prompt
domain: tecnologia
description: Scrive e migliora prompt per modelli linguistici e di immagini: struttura, esempi, vincoli, formato di output, ragionamento e valutazione.
triggers: prompt, scrivi un prompt, migliora il prompt, prompt engineering, istruzioni per l'ai, system prompt, few shot, chain of thought, prompt per chatgpt, template di prompt, come chiedere all'ai, ottimizzare un prompt

**Struttura efficace**: 1) **ruolo/contesto** (chi sei, per chi, in che situazione); 2) **compito** preciso e verificabile; 3) **dati** in blocchi delimitati (`"""…"""` o tag XML) — e dichiara che sono dati, non istruzioni; 4) **vincoli** (lunghezza, tono, cosa evitare, fonti ammesse); 5) **formato di output** (JSON con schema, tabella, elenco); 6) **esempi** (few-shot) del risultato atteso, anche negativi; 7) criteri di qualità e cosa fare se mancano informazioni («chiedi, non inventare»).
**Tecniche**: scomponi i compiti complessi in passi (o in più chiamate), fai ragionare prima di rispondere quando serve, chiedi autovalutazione/revisione, usa temperatura bassa per estrazione e alta per creatività.
**Iterazione**: prova su 5-10 casi reali (compresi quelli difficili), cambia una cosa alla volta, conserva le versioni, misura.
**Output**: il prompt migliorato, spiegando in 3 punti cosa è cambiato e perché, più una variante breve e una più rigorosa.
@@@
name: acquisto-tecnologia
title: Acquistare tecnologia con criterio
domain: tecnologia
description: Aiuta a scegliere e confrontare prodotti tecnologici (PC, telefoni, TV, cuffie, stampanti, fotocamere...) in base a esigenze, specifiche reali e prezzo.
triggers: quale comprare, consigliami un, miglior portatile, confronta, meglio o, che tv comprare, cuffie, stampante, tablet, specifiche, rapporto qualità prezzo, acquisto tecnologico, recensioni, usato o nuovo, offerta amazon, ricondizionato

**Metodo**: 1) **uso reale e budget** (non il «top di gamma»): 3-4 requisiti indispensabili e cosa è facoltativo; 2) specifiche che contano per categoria (portatile: CPU/RAM/SSD, schermo, peso, batteria, tastiera, porte; TV: pannello OLED/QLED/LCD, luminosità, HDMI 2.1, sistema; cuffie: ANC, codec, autonomia, comfort; stampante: costo per pagina, inchiostro vs laser, Wi-Fi); 3) ignora numeri di marketing (megapixel, «fino a», picchi di nits irreali); 4) **costo totale** (consumabili, accessori, assistenza, aggiornamenti software garantiti); 5) recensioni indipendenti (test misurati) e problemi noti; 6) prezzo: storico (non lo sconto «dal prezzo di listino»), negozio affidabile, garanzia legale di 24 mesi, diritto di recesso di 14 giorni online; **ricondizionato** con garanzia può convenire; 7) tempi: nuovo modello in arrivo?
**Output**: tabella di confronto (2-4 opzioni) con pro/contro e una raccomandazione motivata; usa la ricerca web per modelli e prezzi **attuali** e dichiara cosa non hai potuto verificare. Niente link di affiliazione né preferenze di marca immotivate.
@@@
name: backup-e-cloud-storage
title: Backup, archiviazione e cloud
domain: tecnologia
description: Protegge i dati con backup affidabili (regola 3-2-1), sceglie cloud e dischi, organizza i file, ripristina e recupera dopo guasti o ransomware.
triggers: backup, copia di sicurezza, cloud storage, google drive, onedrive, dropbox, ripristino dei dati, recupero dei dati, disco rotto, time machine, 3-2-1, archiviazione foto, hard disk esterno, sincronizzazione, restic, borg

**Principio 3-2-1**: **3** copie dei dati, su **2** supporti diversi, **1** fuori sede (cloud o altro luogo); più una copia **non modificabile/offline** contro il ransomware. **Sincronizzazione ≠ backup**: un file cancellato o cifrato si propaga ovunque; serve la **cronologia delle versioni**.
**Metodo**: 1) elenca i dati insostituibili (foto, documenti, progetti, chiavi/2FA) e dove stanno; 2) automatizza: Cronologia file/Time Machine su disco esterno + backup cifrato nel cloud (Backblaze, restic/borg verso uno storage, o il cloud della piattaforma); 3) **cifra** i backup e conserva la chiave in luogo sicuro; 4) **testa il ripristino** ogni tanto (un backup mai ripristinato non è un backup); 5) dischi: gli HDD si rompono, controlla SMART, sostituisci dopo 4-5 anni; 6) organizza: cartelle semplici, nomi con data ISO (`2026-10-21_…`), niente duplicati.
**Dati persi**: spegni subito il dispositivo, non scrivere sul disco, usa strumenti di recupero su una copia (o un servizio professionale se il disco fa rumori).
**Output**: piano di backup con strumenti, frequenza e costo stimato, e la procedura di verifica.
@@@
name: stampa-3d-e-maker
title: Stampa 3D e fabbricazione digitale
domain: tecnologia
description: Stampa 3D (FDM/resina): scelta della stampante, modellazione, slicer, materiali, parametri, problemi comuni, tolleranze e progettazione per la stampa.
triggers: stampa 3d, stampante 3d, pla, petg, abs, slicer, cura, prusaslicer, stl, fdm, resina, supporti, warping, retraction, stringing, modello 3d da stampare, tolleranze, laser cutter, cnc

**Scelta**: **FDM** (filamento) per prototipi e pezzi funzionali, **resina** per dettagli e miniature (sicurezza: guanti, ventilazione, lavaggio e cura). Per iniziare: macchine già calibrate con piatto livellato automaticamente.
**Materiali**: **PLA** (facile, rigido, poco resistente al calore), **PETG** (resistente, tollerante), **ABS/ASA** (calore e urti, serve camera chiusa e ventilazione), **TPU** (flessibile).
**Progettare per la stampa**: orientamento (i pezzi sono più deboli tra gli strati), sbalzi ≤ 45° senza supporti, pareti ≥ 2-3 linee d'estrusione (≈ 1,2 mm), **tolleranze** 0,2-0,4 mm tra parti mobili, smussi invece di spigoli sul piatto, fori leggermente più grandi, riempimento 15-30% (più perimetri danno più resistenza del riempimento).
**Problemi**: prima il **primo strato** (livello, pulizia, temperatura piatto); stringing → temperatura e retrazione; warping → piatto caldo, adesione, ambiente stabile; sottoestrusione → ugello, flusso, filamento umido (essiccalo).
**Output**: impostazioni di partenza (temperature, velocità, altezza strato) per materiale e stampante, e checklist di diagnosi.
@@@
name: trend-e-hype-tecnologico
title: Valutare novità tecnologiche e hype
domain: tecnologia
description: Giudica nuove tecnologie e tendenze (AI, quantum, blockchain, VR, auto elettriche...) in modo critico: cosa è reale, cosa è marketing, cosa conta per te.
triggers: nuova tecnologia, novità tecnologiche, hype, tendenze tecnologiche, cos'è il metaverso, quantum computing, realtà virtuale, 6g, tecnologia del futuro, vale la pena, è una bolla, innovazione, auto elettrica pro e contro, tecnologia emergente

**Metodo**: 1) **cos'è davvero** in parole semplici e quale problema risolve; 2) **a che punto è**: ricerca, prototipo, prodotto, adozione di massa (maturità, TRL); 3) chi lo sostiene e **con quali incentivi** (aziende, investitori, ricercatori indipendenti); 4) prove: dati misurati, studi peer-reviewed, casi reali riproducibili — non demo o annunci; 5) **limiti e costi** (tecnici, energetici, regolatori, di adozione); 6) alternative già esistenti che fanno meglio o più economicamente; 7) conseguenze per l'utente e orizzonte (adesso / 2-3 anni / oltre); 8) segnali d'allarme: promesse esponenziali, gergo vago, «cambierà tutto», assenza di concorrenti seri, prezzi che salgono senza utenti.
**Output**: scheda sintetica (cos'è, stato, vantaggi, limiti, rischio hype 1-5, cosa fare ora) con fonti verificate (cerca sul web e cita; i dati recenti vanno controllati). Distingui fatti, stime e opinioni.
@@@
name: strumenti-digitali-e-automazioni
title: Strumenti digitali e automazione personale
domain: tecnologia
description: Organizza lavoro e vita digitale con gli strumenti giusti: note, task, calendario, file, automazioni (Notion, Obsidian, Zapier, scorciatoie).
triggers: notion, obsidian, app per appunti, organizzare i file, app per le attività, automazioni personali, scorciatoie, zapier, ifttt, tasker, produttività digitale, second brain digitale, todoist, calendario digitale, sistema di note, workflow digitale

**Metodo**: 1) **un posto solo** per ogni tipo di informazione (note, attività, calendario, file, segreti) e regole di nome/cartella semplici; 2) **cattura veloce** (un gesto per annotare: widget, comando a JARVIS, scorciatoia) → riordino periodico; 3) note collegate (Obsidian/Notion) con pochi tag e link tra argomenti, niente cartelle profondissime; 4) attività con prossimo passo e data, calendario solo per ciò che ha un'ora; 5) **automatizza il ripetitivo**: regole email, scorciatoie del telefono/PC, flussi tra app (n8n, Zapier, Make, Power Automate), script; calcola il tempo risparmiato prima di costruire; 6) **meno strumenti**: aggiungine uno solo se risolve un problema concreto; 7) backup ed esportazione in formati aperti (Markdown, CSV).
**Con JARVIS**: promemoria e liste (`remind_in`, `task_add`), secondo cervello (`brain_add_note`, `brain_search`), calendario e posta (se Google è collegato).
**Output**: sistema proposto (cosa va dove), 3 automazioni a più alto rendimento con i passaggi e un piano di adozione graduale di una settimana.
