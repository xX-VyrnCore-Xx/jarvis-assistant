name: cybersecurity-difensiva
title: Cybersecurity difensiva e hardening
domain: tecnologia
description: Mette in sicurezza account, dispositivi, reti e piccoli server: minacce comuni, configurazioni sicure, monitoraggio e risposta a un incidente.
triggers: cybersecurity, sicurezza informatica, hardening, firewall, antivirus, ransomware, attacco hacker, account violato, vulnerabilità, patch, malware, firewall, sicurezza del server, incidente di sicurezza, phishing, difendersi

**Metodo**: 1) **modello delle minacce**: cosa proteggo, da chi, con quale impatto; 2) priorità ad alto rendimento: aggiornamenti automatici, **password uniche + gestore + passkey/2FA** (preferire app o chiavi hardware a SMS), backup 3-2-1 offline, disco cifrato; 3) riduci la superficie: servizi inutili spenti, privilegi minimi, niente porte aperte inutili, SSH con chiavi, fail2ban; 4) segmenta e controlla (log, avvisi, scansioni di vulnerabilità); 5) **se sospetti una violazione**: isola il dispositivo, cambia le password da un dispositivo pulito, revoca sessioni e token, controlla inoltri email e regole nascoste, ripristina da backup, avvisa chi serve (GDPR: 72 ore per i dati personali).
**Output**: lista di controllo ordinata per priorità con comandi o passaggi concreti. Solo difesa e sistemi propri o autorizzati; niente istruzioni offensive.
@@@
name: crittografia-pratica
title: Crittografia pratica
domain: tecnologia
description: Spiega e applica cifratura, hash, firme, TLS, gestione delle chiavi e errori da evitare, con strumenti collaudati e mai algoritmi inventati.
triggers: crittografia, cifratura, hash, aes, rsa, chiave pubblica, tls, certificato, firma digitale, bcrypt, argon2, gpg, cifrare i dati, end to end, salt, token jwt, gestione delle chiavi

**Regole**: 1) **mai inventare algoritmi**: usa librerie collaudate (libsodium, `cryptography`, WebCrypto); 2) simmetrica **AES-256-GCM** o ChaCha20-Poly1305 con nonce unico; 3) chiavi: derivate con HKDF/Argon2, mai in codice o repository, ruotate, con permessi minimi; 4) password: **Argon2id/bcrypt** con salt, mai hash veloci (MD5/SHA-1/SHA-256 puri); 5) integrità e firme: HMAC, Ed25519; 6) trasporto: TLS 1.2+/1.3, certificati validi, HSTS; 7) JWT: algoritmo fissato, scadenza breve, segreto forte; 8) casi d'uso: cifrare a riposo, a riposo+ricerca (indici ciechi), end-to-end.
**Errori tipici**: nonce riusato, ECB, confrontare MAC con `==` (usa confronto a tempo costante), chiave derivata da testo debole. **Output**: codice minimo corretto, dove sta la chiave, cosa NON protegge (metadati, endpoint compromesso).
@@@
name: reti-vpn-e-dns
title: Reti avanzate, VPN, DNS e proxy
domain: tecnologia
description: Diagnostica e configura reti: IP, DNS, porte, NAT, VPN (WireGuard), firewall, proxy e problemi di connessione o di latenza.
triggers: dns, vpn, wireguard, firewall, porte aperte, nat, ip pubblico, proxy, latenza, ping, traceroute, rete lenta, port forwarding, subnet, dhcp, cloudflare, reverse proxy, non si connette

**Metodo**: 1) isola il livello: fisico/wifi → IP/gateway → DNS → porta/servizio → applicazione; 2) comandi: `ping`, `traceroute`/`tracert`, `nslookup`/`dig`, `curl -v`, `ss -tulpn`/`netstat`, `ip a`; 3) DNS: record A/AAAA/CNAME/MX/TXT, TTL e propagazione; 4) NAT e port forwarding: porta, protocollo, IP locale fisso, CGNAT del provider (niente IP pubblico); 5) **WireGuard**: coppia di chiavi per peer, AllowedIPs, porta UDP, MTU; 6) reverse proxy (Caddy/nginx) con TLS automatico; 7) firewall: default deny, regole minime.
**Output**: ipotesi ordinate per probabilità con il comando che le conferma, poi la correzione. Cambiare DNS/firewall può togliere l'accesso: indica come tornare indietro.
@@@
name: blockchain-e-smart-contract
title: Blockchain, smart contract e Web3
domain: tecnologia
description: Spiega blockchain, wallet, transazioni, smart contract e DeFi con rischi reali, costi e alternative semplici.
triggers: blockchain, smart contract, wallet, ethereum, solidity, nft, defi, web3, token, seed phrase, commissioni gas, staking, dapp, ledger, bitcoin

**Metodo**: 1) **serve davvero una blockchain?** (più parti che non si fidano, nessun intermediario comune): spesso un database basta; 2) concetti: blocchi, consenso (PoW/PoS), transazioni, commissioni, finalità; 3) **wallet**: la seed phrase è tutto (mai digitarla online, mai a nessuno, backup offline), hardware wallet per cifre importanti; 4) smart contract (Solidity): immutabili, quindi test estesi, audit, upgrade pattern, attenzione a reentrancy, overflow, permessi; 5) costi e velocità (gas, layer 2); 6) rischi: truffe, rug pull, bridge violati, volatilità, aspetti fiscali (in Italia i cripto-asset hanno obblighi dichiarativi).
**Output**: spiegazione neutrale con pro e contro; per sviluppo, struttura del contratto e test. Nessuna consulenza d'investimento; prezzi dal vivo con `crypto_price`.
@@@
name: quantum-e-calcolo-emergente
title: Quantum computing e tecnologie emergenti
domain: tecnologia
description: Spiega in modo onesto calcolo quantistico, chip, robotica, realtà aumentata e altre tecnologie emergenti, separando realtà, promesse e tempi.
triggers: quantum computing, computer quantistico, qubit, tecnologie emergenti, realtà aumentata, realtà virtuale, robotica, chip, semiconduttori, fusione nucleare, 6g, computer neuromorfico, edge computing

**Metodo**: 1) cos'è e quale problema risolve; 2) **stato reale** con dati recenti (`news_headlines` categoria tecnologia/scienza): prototipi, prodotti, benchmark; 3) livelli di maturità (idea → laboratorio → prodotto → adozione); 4) limiti fisici ed economici (errori nei qubit, costi, consumi); 5) chi ne beneficia davvero e quando, con scenari e incertezza; 6) cosa imparare o seguire.
**Esempi**: i computer quantistici non «provano tutte le soluzioni insieme»: aiutano su classi specifiche (fattorizzazione, simulazione chimica), non sostituiscono il PC; la crittografia post-quantistica (NIST) si adotta già ora. **Output**: spiegazione semplice, scala di maturità, 2 fonti da seguire.
@@@
name: open-data-e-api-pubbliche
title: Open data e API pubbliche gratuite
domain: tecnologia
description: Trova e usa dati aperti e API gratuite (meteo, terremoti, finanza, trasporti, ISTAT, Wikipedia) con limiti, licenze e codice di esempio.
triggers: api gratuite, open data, dati aperti, api pubblica, dataset gratuito, istat, open-meteo, usgs, wikipedia api, dati in tempo reale, rss, json api, quale api uso, fonte di dati

**Metodo**: 1) cosa serve e con quale freschezza; 2) fonti affidabili: **ISTAT, Eurostat, data.gov, dati.gov.it, Banca d'Italia, BCE**, Open-Meteo, USGS (terremoti), Wikipedia/Wikidata, OpenStreetMap, NASA, CoinGecko, frankfurter.app; 3) leggi **licenza** (CC-BY: cita la fonte), limiti di richieste e termini d'uso; 4) chiamata minima con `requests`/`httpx` e timeout, gestione errori, cache; 5) formato (JSON, CSV, RSS/Atom) e schema; 6) nessuna chiave nei repository.
**Output**: endpoint con parametri, esempio di risposta, codice breve, e come tenere i dati aggiornati (cache + aggiornamento periodico). Per feed di notizie JARVIS offre `feed_add` per aggiungere un RSS personale.
@@@
name: diritto-digitale-gdpr-e-copyright
title: Diritto digitale, GDPR e copyright
domain: tecnologia
description: Orienta su privacy dei dati personali, licenze, copyright, contratti online e responsabilità, senza sostituire un avvocato.
triggers: gdpr, privacy policy, cookie banner, copyright, diritto d'autore, licenza, termini di servizio, dati personali, informativa privacy, dpo, consenso, trattamento dei dati, marchio, responsabilità online

**Metodo**: 1) quali **dati personali** si trattano e con quale base giuridica (consenso, contratto, obbligo, interesse legittimo); 2) principi: minimizzazione, finalità, conservazione limitata, sicurezza (cifratura, accessi), trasparenza; 3) diritti dell'interessato: accesso, rettifica, cancellazione, portabilità; risposta entro 1 mese; 4) fornitori: contratto/DPA e trasferimenti extra-UE; 5) violazioni: notifica al Garante entro 72 ore se rischio; 6) **copyright**: opere protette salvo licenza; licenze aperte (MIT, GPL, CC-BY) hanno condizioni; eccezioni limitate (citazione), non il «uso personale» generico; 7) contratti e termini: durata, recesso, responsabilità.
**Output**: lista di adempimenti pratici e documenti da preparare. Le norme cambiano: indica di verificare su fonti ufficiali (Garante Privacy, EUR-Lex) e di consultare un professionista per casi seri.
