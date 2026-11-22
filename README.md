# i-gea
i-Gea Kinect Rehab Coach  Sistema agentico multi-AI per la riabilitazione fisioterapica guidata da sensore Kinect V2.

Autori: Benedetta Gamba, Niccolò Rizzi, Chiara Zuccaretti
Progetto sviluppato per bioERGOtech — Agentic AI High School Innovation Program

---

## Indice

1. Panoramica
2. Architettura generale
3. Requisiti hardware
4. Requisiti software e dipendenze
5. Installazione e configurazione
6. Struttura del progetto
7. Funzionalità implementate
8. Architettura del workflow n8n
9. Comandi e controlli utente
10. Flusso completo di una sessione
11. Parametri di configurazione
12. Formati dei dati scambiati
13. Logging e output
14. Costi operativi
15. Privacy e sicurezza
16. Limitazioni note
17. Scelta del sensore e alternative future

---

## 1. Panoramica

Kinect Rehab Coach è un sistema software che assiste il paziente durante una sessione di riabilitazione fisioterapica. Il sistema:

- riceve una diagnosi scritta in linguaggio naturale
- genera un programma riabilitativo strutturato composto da uno o più esercizi
- guida il paziente nell'esecuzione di ogni esercizio, suddiviso in fasi
- rileva le compensazioni posturali in tempo reale
- fornisce feedback correttivi immediati (calcolati localmente) e contestuali (generati da agenti AI)
- adatta i target articolari in base all'esecuzione effettiva del paziente
- produce un report narrativo finale

Il sistema utilizza un sensore di profondità Microsoft Kinect V2 per il tracciamento dello scheletro (25 giunti, 30 FPS), un motore Python per il calcolo geometrico e la gestione del flusso, e un'architettura multi-agente basata su n8n e DeepSeek per la generazione e l'adattamento dei contenuti intelligenti.

Il principio architetturale fondamentale è la separazione netta tra componenti deterministiche e componenti AI: il calcolo degli angoli articolari, la verifica delle soglie e il conteggio delle ripetizioni sono eseguiti da codice Python e JavaScript, mentre la generazione del programma, la valutazione contestuale, il feedback empatico e la pianificazione adattiva sono delegati a modelli linguistici. Questo garantisce che il sistema sia reattivo (latenza locale inferiore a 50 ms) e che i numeri critici non siano mai soggetti ad allucinazione.

---

## 2. Architettura generale

Il sistema è composto da tre livelli:

**Livello sensoriale e di calcolo locale (Python)**
- Acquisizione frame dal Kinect V2 (colore + profondità + scheletro)
- Calcolo degli angoli articolari tra giunti
- Calcolo delle compensazioni rispetto alla baseline individuale
- Classificazione della postura
- Gestione della macchina a stati della sessione
- Rendering dell'interfaccia OpenCV
- Sintesi vocale (TTS)

**Livello di orchestrazione agentica (n8n)**
- Sette agenti AI specializzati
- Quattro endpoint webhook
- Validazione strutturale dei payload
- Logica di routing e di coordinamento

**Livello di intelligenza (DeepSeek)**
- Modello deepseek-v4-pro per compiti complessi (generazione programma, validazione clinica, pianificazione)
- Modello deepseek-flash per compiti rapidi (routing, feedback breve, report)

I tre livelli comunicano tramite HTTP su localhost. Il livello Python invia richieste asincrone in thread separati, in modo che il loop di acquisizione Kinect non sia mai bloccato da latenze di rete o di inferenza.

---

## 3. Requisiti hardware

- Sensore Microsoft Kinect V2 con adattatore USB 3.0
- PC Windows 10 o Windows 11, 64 bit
- Processore: Intel Core i5 o superiore
- RAM: 8 GB minimo, 16 GB consigliati
- Porta USB 3.0 nativa (non hub)
- Connessione internet per le chiamate agli agenti AI

Il Kinect deve essere posizionato in modo che il paziente sia interamente visibile, a una distanza di 1,5-3 metri, con illuminazione ambientale adeguata.

---

## 4. Requisiti software e dipendenze

**Runtime e linguaggi**
- Python 3.10 o superiore
- Kinect SDK 2.0 (runtime Microsoft)
- Docker Desktop (per n8n)

**Dipendenze Python** (file `requirements.txt`)
kinect-next>=1.0.0
opencv-python>=4.8.0
requests>=2.31.0
pyttsx3>=2.90
text

**Applicazioni esterne**
- n8n Community Edition (Docker, porta 5678)
- API DeepSeek con chiave di accesso valida

**Voci SAPI5 per TTS**
Su Windows è necessario che sia installata almeno una voce italiana. Se non presente, il TTS usa la voce di default del sistema (tipicamente inglese). Per installarla: Impostazioni > Data/ora e lingua > Riconoscimento vocale > Aggiungi voce.

---

## 5. Installazione e configurazione

**Passo 1 — Clonare il repository**

git clone <URL_REPO>
cd kinect-rehab-coach
text


**Passo 2 — Installare le dipendenze Python**

pip install -r requirements.txt
text


**Passo 3 — Avviare n8n in Docker**

docker run -it --rm --name n8n -p 5678:5678 -v n8n_data:/home/node/.n8n docker.n8n.io/n8nio/n8n

**Passo 4 — Importare il workflow n8n**

Aprire l'interfaccia n8n su `http://localhost:5678`, selezionare Workflow > Import from file, e caricare il file `workflow_kinect.json`.

**Passo 5 — Configurare la credenziale DeepSeek**

In n8n: Credentials > Add Credential > OpenAI (DeepSeek è compatibile con l'API OpenAI). Inserire:
- API Key: la propria chiave DeepSeek
- Base URL: https://api.deepseek.com/v1

Salvare con nome riconoscibile (per esempio "DeepSeek account").

**Passo 6 — Assegnare la credenziale ai nodi**

Nel workflow importato, aprire ciascun nodo di tipo chat model (nomi che iniziano con "DS") e selezionare la credenziale DeepSeek appena creata. I nodi sono:
- DS Pro Program Designer
- DS Pro Critic
- DS Flash Orchestrator
- DS Flash Coach_fast
- DS Flash Coach_deep
- DS Pro Planner
- DS Flash Reporter

**Passo 7 — Attivare il workflow**

Attivare il workflow con il toggle in alto a destra. Lo stato deve essere "Active".

**Passo 8 — Verificare i webhook**

I quattro webhook devono rispondere sui path:
- kinect-recipe
- kinect-feedback
- kinect-plan
- kinect-report

**Passo 9 — Avviare il sistema**
python main_kinect.py

---

## 6. Struttura del progetto

**File Python**

`main_kinect.py`
Punto di ingresso del programma. Gestisce:
- logging completo su file (debug.log) tramite classe Tee
- acquisizione frame dal Kinect
- rilevamento del corpo tracciato
- verifica del tracking dei giunti richiesti
- calcolo delle metriche per frame
- dispatch degli input (SPAZIO, R, N, C, V, ESC)
- rendering tramite render_sessione
- gestione degli errori per frame con anti-spam

`analisi_angoli.py`
Funzioni geometriche e di analisi:
- calcola_angolo(p1, p2, p3): angolo tra tre punti 3D
- angolo_tra_giunti(joints, nomi): wrapper su tre giunti del Kinect
- inclinazione_verticale(joints, a, b): angolo rispetto all'asse verticale
- distanza_verticale_giunti(joints, a, b): differenza verticale in centimetri
- valore_compensazione(joints, comp): dispatch sui tipi di compensazione supportati
- giunti_richiesti_da_ricetta(ricetta): estrae l'insieme di giunti usati da target e compensazioni
- articolazioni_tracciate(joints, nomi): verifica che tutti i giunti siano TRACKED
- classifica_postura(joints): restituisce in_piedi, seduto, sdraiato, inginocchiato, accovacciato o sconosciuta

`stato_step.py`
Implementazione dei cinque tipi di fase. Ogni fase è gestita da una classe che eredita da StepHandler e implementa il metodo update(metriche, errori_comp), restituendo un StepResult.
- RepsStep: ripetizioni cicliche con isteresi su min/max
- HoldIsometricStep: mantenimento statico per N secondi
- MovementStep: raggiungimento di un target (con from_range opzionale)
- RestStep: pausa temporizzata
- CustomRulesStep: combinazione di condizioni primitive (target_in_range, reps_completed, hold_for) con combinatori all_of / any_of
Il registry STEP_HANDLERS mappa i nomi dei tipi alle classi. La factory crea_handler costruisce l'handler a partire dalla configurazione della fase.

`esercizio.py`
Classe EsercizioHandler. Gestisce il ciclo di vita di un singolo esercizio:
- stato ISTRUZIONI: mostra le istruzioni, attende SPAZIO
- stato COUNTDOWN: 3 secondi di preparazione
- stato CALIBRAZIONE: raccoglie campioni per misurare il range articolare reale, valida il range minimo, calcola la baseline delle compensazioni, applica il clamp ai target delle fasi
- stato ESECUZIONE: esegue le fasi in sequenza, ciclando per target_repetitions volte
- stato COMPLETATO: segnala il completamento
Accumula tutti gli errori visti durante ogni fase (non solo quelli del frame finale) e registra se la fase è stata adattata dal Planner. Espone callback on_step_complete e on_plan_request per la comunicazione con n8n.

`sessione_programma.py`
Classe SessioneProgramma. Gestisce l'intera sessione:
- richiesta del programma (con gestione del giro di chiarimenti)
- gestione delle revisioni del programma (max 2 tentativi)
- ciclo sugli esercizi
- transizione di 4 secondi tra esercizi con schermata dedicata
- inoltro delle richieste agli endpoint n8n
- ricezione e smistamento delle risposte (feedback, plan_delta, report)
- gestione del plan_delta pendente con scarto se la fase non è più corrente
- salvataggio del report su file
- accumulo del program_context per il report finale

`n8n_client.py`
Client HTTP asincrono. Implementa:
- HistoryBuffer: coda delle ultime 5 fasi/rep con metriche ed errori
- _post_async: wrapper che esegue la chiamata in un thread separato e invoca il callback al termine
- invia_richiesta_programma: richiesta al Program Designer (con supporto per chiarimenti e revisioni)
- invia_evento_step: invio di una valutazione di fase o di ripetizione
- invia_piano: richiesta al Planner
- invia_report: richiesta al Reporter

`render_step.py`
Rendering dell'interfaccia tramite OpenCV. Funzioni principali:
- render_sessione: dispatch sullo stato della sessione
- _render_attesa, _render_errore, _render_chiarimenti: stati semplici
- _render_programma_pronto: schermata di conferma del programma con opzioni SPAZIO/R/ESC
- _render_transizione: pausa tra esercizi con riepilogo e countdown
- _render_esercizio: schermata principale di esecuzione con lista esercizi, pannello fasi, preview, footer
- _render_istruzioni_calibrazione: interfaccia dedicata a ISTRUZIONI, COUNTDOWN e CALIBRAZIONE
- _render_pannello_esercizio: pannello destro con dettaglio fase corrente
- _render_footer: postura e feedback AI

`tts_manager.py`
Gestore TTS con coda prioritaria. Implementa:
- thread worker singolo (pyttsx3 non è thread-safe)
- coda FIFO con scarto del messaggio più vecchio se la coda supera la dimensione massima
- rate limit per evitare letture ravvicinate
- priorità normal (feedback) e high (report finale)
- toggle on/off

`preview_animation.py`
Anteprima animata del movimento atteso. Disegna un omino stilizzato con il segmento del giunto target che oscilla tra i valori della fase corrente. Supporta otto template specifici (shoulder, elbow, hip, knee, left e right) e un fallback generico per gli altri giunti. Ottimizzata per lavorare solo sulla regione di interesse del pannello, senza copiare l'intera immagine.

**File di configurazione**

`requirements.txt`
Elenco delle dipendenze Python.

`workflow_kinect.json`
Workflow n8n completo con tutti i nodi e le connessioni. Da importare in n8n.

**File generati a runtime (da escludere dal repository)**

`debug.log`
Log completo della sessione corrente, sovrascritto ad ogni avvio.

`reports/session-<timestamp>.txt`
Report narrativo e program_context di ogni sessione completata.

---

## 7. Funzionalità implementate

### 7.1 Generazione del programma

L'utente digita una diagnosi in linguaggio naturale. Il Program Designer analizza la richiesta e decide autonomamente se procedere alla generazione o chiedere chiarimenti.

Se la diagnosi è ambigua o mancano informazioni clinicamente rilevanti (fase del trattamento, zona del corpo, controindicazioni), il Program Designer restituisce un massimo di tre domande di chiarimento. Il sistema le mostra nel terminale e raccoglie le risposte. Al secondo giro il Program Designer è obbligato a generare, senza ulteriori domande.

Il programma generato contiene:
- nome e descrizione
- durata stimata in minuti
- lista di esercizi, ciascuno con:
  - identificativo univoco
  - nome
  - istruzioni per il paziente (paragrafo di 3-4 frasi in linguaggio semplice)
  - postura richiesta
  - numero di ripetizioni (target_repetitions)
  - lista di target articolari (ciascuno con 3 giunti e range atteso)
  - lista di compensazioni da monitorare
  - lista di fasi

### 7.2 Validazione e correzione del programma

Ogni programma passa attraverso un nodo di validazione strutturale che verifica:
- validità del JSON
- presenza dei campi obbligatori
- correttezza dei target (esattamente 3 giunti)
- coerenza dei joint_id delle fasi con i target dichiarati
- presenza dei campi specifici per tipo di fase
- limiti dimensionali (massimo 10 esercizi, massimo 8 fasi per esercizio)

Il validatore esegue anche un auto-fix per i casi più comuni di errore del modello:
- target_joints rappresentato come array di array invece che array di oggetti
- compensazioni prive di id o di feedback_message

Successivamente il Critic, un secondo agente AI, rivalida la coerenza clinica del programma: plausibilità dei range, pertinenza delle compensazioni, chiarezza delle istruzioni, assenza di controindicazioni. Il Critic può approvare o proporre una correzione, che viene a sua volta validata strutturalmente prima di essere accettata.

### 7.3 Human-in-the-loop

Prima dell'inizio della sessione, il sistema mostra all'utente il programma generato con le istruzioni complete di ogni esercizio. L'utente può:
- confermare e iniziare (tasto SPAZIO)
- chiedere modifiche all'AI (tasto R): scrive in linguaggio naturale cosa vuole cambiare, il sistema invia la richiesta con la nota e il programma precedente al Program Designer, che rigenera il programma. Sono consentiti al massimo due tentativi di revisione.
- uscire (tasto ESC)

### 7.4 Calibrazione personalizzata

Per ogni esercizio, prima dell'esecuzione, il sistema esegue una calibrazione. L'utente esegue il movimento dell'esercizio per due volte, in modo lento e ampio. Il sistema raccoglie un minimo di 15 campioni e calcola:
- range articolare effettivo (minimo e massimo osservati)
- baseline delle compensazioni (media dei primi 15 campioni a riposo)

Il range misurato viene utilizzato per adattare i target dichiarati nella ricetta. Se un target è completamente al di fuori del range dell'utente, il sistema lo ancora al limite mantenendo la larghezza originale, evitando di comprimerlo a zero. Se un target è parzialmente dentro, viene clampato solo il lato eccedente.

La calibrazione viene validata: se il range osservato è inferiore a 20 gradi, viene rifiutata e l'utente deve ripetere il movimento.

L'utente può in qualsiasi momento riavviare la calibrazione dell'esercizio corrente tramite il tasto C.

### 7.5 Sistema a fasi

Ogni esercizio è suddiviso in fasi. Ogni fase ha un tipo e un criterio di completamento.

Tipi supportati:
- reps: l'utente deve eseguire N ripetizioni cicliche tra due valori di angolo
- hold: l'utente deve mantenere una posizione per N secondi, senza compensazioni attive
- movement: l'utente deve raggiungere un range target partendo da un range iniziale
- rest: pausa temporizzata senza controlli
- custom_rules: combinazione di condizioni primitive

Per ogni fase il sistema mostra:
- descrizione dell'azione richiesta
- progresso (0-100%)
- messaggio contestuale (angolo corrente, tempo trascorso, condizione da soddisfare)
- eventuali errori di compensazione attivi

### 7.6 Ciclo di ripetizioni a livello esercizio

Se un esercizio contiene più fasi che rappresentano una singola ripetizione completa (per esempio preparazione, movimento, mantenimento, ritorno), il sistema ripete l'intera sequenza di fasi per un numero di volte pari a target_repetitions.

Se un esercizio contiene una sola fase di tipo reps, il conteggio delle ripetizioni è gestito internamente dalla fase e target_repetitions vale 1.

### 7.7 Compensazioni posturali

Il sistema monitora le compensazioni dichiarate nella ricetta. Ogni compensazione ha:
- un identificativo
- un tipo (angle, angle_from_vertical, distance_vertical)
- una lista di giunti
- una soglia massima (max_allowed)
- un messaggio di correzione

Per ogni frame, il sistema calcola il valore attuale della compensazione e lo confronta con la baseline individuale. Se lo scostamento supera la soglia, l'errore è segnalato visivamente con bordo rosso e messaggio di correzione.

Tutti gli errori visti durante una fase (non solo quelli del frame finale) vengono accumulati e registrati nel program_context, così che il report finale rifletta la storia completa della sessione.

### 7.8 Classificazione della postura

Il sistema classifica la postura del corpo in cinque categorie più una di fallback:
- in_piedi
- seduto
- sdraiato
- inginocchiato
- accovacciato
- sconosciuta

La classificazione utilizza tre segnali combinati: angolo medio delle ginocchia, inclinazione del tronco rispetto alla verticale, differenza verticale tra testa e bacino. Se la postura richiesta dalla ricetta non corrisponde a quella rilevata, appare un avviso visivo non bloccante.

### 7.9 Orchestrazione del feedback

Per ogni fase completata, il sistema costruisce un payload contenente le metriche correnti, i target da verificare, le compensazioni da verificare e la history delle ultime cinque fasi o ripetizioni.

Il valutatore deterministico (JavaScript) confronta le metriche con i target e con le soglie delle compensazioni, producendo un risultato binario (target_ok) e una lista di errori riscontrati.

L'Orchestratore (LLM) riceve questo risultato e la history e decide il percorso di feedback:
- fast: il feedback è generato da Coach_fast, modello rapido, massimo due frasi
- deep: il feedback è generato da Coach_deep, con accesso alla history e focus specifico

L'Orchestratore sceglie deep quando ci sono errori, quando lo stesso errore si è ripetuto più volte, o quando la situazione è ambigua.

### 7.10 Feedback vocale

Tutti i feedback generati dai Coach vengono letti ad alta voce tramite pyttsx3, in un thread separato. Il TTS applica:
- rate limit di 2 secondi tra letture
- coda massima di 2 messaggi in attesa
- priorità alta per il report finale
- disattivazione tramite tasto V

### 7.11 Anteprima animata

Durante l'esecuzione di ogni fase, un pannello in basso a destra mostra un omino stilizzato con il segmento del giunto target animato. Il segmento oscilla tra i valori attesi della fase corrente, e un indicatore mostra la posizione attuale del giunto misurata dal Kinect.

Il pannello supporta otto template specifici (spalla, gomito, anca, ginocchio, lato destro e sinistro) e un fallback generico per gli altri giunti.

### 7.12 Planner adattivo

Ogni cinque ripetizioni, oppure in caso di stallo superiore a 15 secondi, il sistema invia una richiesta al Planner con il programma corrente, i target della fase attiva e le metriche recenti.

Il Planner può suggerire:
- riduzione o ampliamento del range target
- modifica della durata di un hold
- modifica del numero di ripetizioni
- skip della fase corrente

Se il suggerimento arriva quando la fase è ancora attiva, viene applicato e la fase viene marcata come adattata dal Planner. Se arriva dopo il cambio di fase o di esercizio, viene scartato.

### 7.13 Transizione tra esercizi

Al completamento di un esercizio, se esiste un esercizio successivo, il sistema entra in una pausa di 4 secondi. Durante la pausa:
- mostra il nome dell'esercizio completato
- mostra il nome dell'esercizio successivo
- mostra una barra di progresso del countdown
- mostra il feedback AI dell'esercizio appena completato, se arrivato nel frattempo

Trascorsi i 4 secondi, l'esercizio successivo parte automaticamente con il proprio countdown di 3 secondi.

### 7.14 Report narrativo finale

Al termine dell'ultimo esercizio, il sistema invia al Reporter un riepilogo strutturato della sessione:
- nome e descrizione del programma
- durata in secondi
- numero di esercizi completati sul totale
- per ogni esercizio: ripetizioni, fasi completate, fasi saltate, numero di fasi adattate dal Planner, errori accumulati

Il Reporter genera un paragrafo narrativo di 3-5 frasi in italiano, con tono incoraggiante ma onesto, che riassume cosa è stato fatto, i punti di forza, le aree di miglioramento e un suggerimento per la prossima volta.

Il report viene:
- mostrato a schermo nella schermata di completamento
- letto ad alta voce con priorità alta
- salvato in `reports/session-<timestamp>.txt` insieme al program_context completo

### 7.15 Logging

Tutto l'output del programma viene scritto simultaneamente sul terminale e sul file `debug.log` tramite una classe Tee. Le eccezioni non gestite vengono catturate tramite sys.excepthook e loggate con traceback completo. Il file di log è sovrascritto ad ogni avvio.

---

## 8. Architettura del workflow n8n

Il workflow è composto da quattro endpoint webhook e sette agenti AI.

**Webhook kinect-recipe**
Riceve la richiesta di generazione del programma. Contiene:
- Program Designer (deepseek-v4-pro)
- validatore strutturale (JavaScript)
- Critic (deepseek-v4-pro)
- validatore della correzione del Critic (JavaScript)

**Webhook kinect-feedback**
Riceve gli eventi di valutazione di fase o ripetizione. Contiene:
- switch sull'azione (evaluate_step o evaluate_rep)
- Valutatore Deterministico (JavaScript, non LLM)
- Orchestratore (deepseek-flash)
- validatore del routing (JavaScript)
- switch fast/deep
- Coach_fast (deepseek-flash)
- Coach_deep (deepseek-flash)
- validatore del feedback (JavaScript)

**Webhook kinect-plan**
Riceve le richieste di pianificazione. Contiene:
- Planner (deepseek-v4-pro)
- validatore del piano (JavaScript)

**Webhook kinect-report**
Riceve le richieste di report finale. Contiene:
- Reporter (deepseek-flash)
- validatore del report (JavaScript)

Ogni agente ha un system message dedicato che definisce ruolo, regole, formato di output e vincoli. Tutti gli agenti restituiscono JSON strutturati, validati a valle da nodi JavaScript prima di essere restituiti a Python.

---

## 9. Comandi e controlli utente

**Nella schermata programma pronto**
- SPAZIO: conferma il programma e avvia il primo esercizio
- R: richiede modifiche al Program Designer (massimo due tentativi)
- ESC: esce senza iniziare

**Durante l'esecuzione**
- SPAZIO: conferma l'azione corrente (in ISTRUZIONI avvia il countdown, in CALIBRAZIONE conferma la calibrazione)
- N: salta la fase corrente
- C: riavvia la calibrazione dell'esercizio corrente
- V: attiva o disattiva il TTS
- ESC: esce dal sistema

**Nel terminale (fase pre-Kinect)**
- INVIO: conferma la diagnosi o la risposta a una domanda di chiarimento
- q: esce dal sistema dopo la generazione del programma
- s: riprova la generazione in caso di errore

---

## 10. Flusso completo di una sessione

1. Il programma stampa l'ID sessione e chiede la diagnosi.
2. L'utente digita la diagnosi in linguaggio naturale.
3. Il sistema invia la richiesta a n8n. Il Program Designer elabora.
4. Se il Program Designer chiede chiarimenti, il sistema li mostra e raccoglie le risposte, poi rinvia la richiesta.
5. Il programma generato viene validato strutturalmente e clinicamente.
6. Il sistema mostra il programma a schermo con le istruzioni complete.
7. L'utente conferma con SPAZIO, oppure chiede modifiche con R, oppure esce con ESC.
8. Per ogni esercizio:
   - Mostra le istruzioni dell'esercizio
   - Attende SPAZIO
   - Esegue countdown di 3 secondi
   - Esegue calibrazione: l'utente esegue il movimento due volte, il sistema misura il range
   - Attende SPAZIO per confermare
   - Esegue le fasi in sequenza, ciclando per target_repetitions volte
   - Durante l'esecuzione calcola angoli e compensazioni, mostra feedback locale, invia feedback AI, riceve plan_delta dal Planner
   - Al termine dell'esercizio, mostra la transizione di 4 secondi
9. Al termine dell'ultimo esercizio, invia la richiesta di report al Reporter.
10. Mostra il report narrativo a schermo e lo legge ad alta voce.
11. Salva il report in `reports/`.
12. Stampa il riepilogo finale a terminale.

---

## 11. Parametri di configurazione

I parametri principali sono definiti come costanti nei file Python.

**In esercizio.py**
- COUNTDOWN_SECONDI: 3.0 (durata del countdown prima della calibrazione)
- MIN_CAMPIONI_CALIBRAZIONE: 15 (numero minimo di campioni per calibrare)
- RANGE_MINIMO_CALIBRAZIONE: 20.0 (range minimo in gradi per accettare la calibrazione)
- MARGINE_CLAMP: 0.05 (margine del 5% sul range calibrato per il clamp dei target)
- STALL_TIMEOUT_SECONDI: 15.0 (tempo di stallo prima di richiedere il Planner)
- MAX_PLAN_REQUESTS_PER_PHASE: 2 (numero massimo di richieste al Planner per fase)
- MIN_TARGET_WIDTH: 10.0 (larghezza minima di un target dopo il clamp)

**In sessione_programma.py**
- PAUSA_TRA_ESERCIZI_SECONDI: 4.0 (durata della transizione tra esercizi)
- MAX_REVISIONI: 2 (numero massimo di revisioni del programma)

**In n8n_client.py**
- TIMEOUT_PROGRAMMA: 180 (secondi)
- TIMEOUT_FEEDBACK: 30 (secondi)
- TIMEOUT_PLAN: 60 (secondi)
- TIMEOUT_REPORT: 30 (secondi)

**In tts_manager.py**
- MAX_QUEUE_SIZE: 2 (messaggi in coda)
- MIN_INTERVAL_SECONDI: 2.0 (rate limit tra letture)

**In main_kinect.py**
- TIMEOUT_ATTESA_PROGRAMMA: 180 (secondi)
- MAX_ERRORI_RIPETUTI: 20 (soglia di uscita per errori consecutivi identici)
- SOGLIA_MESSAGGIO_KO: 10 (frame di debounce per il messaggio di tracking assente)

---

## 12. Formati dei dati scambiati

**Richiesta di generazione programma (Python -> n8n)**
```json
{
  "action": "generate_recipe",
  "diagnosis": "string",
  "answers": ["string", "..."],
  "previous_questions": ["string", "..."],
  "revision_note": "string",
  "previous_program": { ... }
}

I campi answers, previous_questions, revision_note e previous_program sono opzionali.

Risposta di generazione programma (n8n -> Python)
json

{
  "action": "clarify",
  "questions": ["string", "..."],
  "_corrected": true,
  "_warning": "string"
}
```
oppure
```
json

{
  "action": "generate",
  "program": {
    "program_name": "string",
    "program_description": "string",
    "estimated_duration_min": 8,
    "steps": [
      {
        "id": "ex_1",
        "exercise_name": "string",
        "patient_instructions": "string",
        "required_posture": "seduto",
        "target_repetitions": 3,
        "target_joints": [
          {
            "id": "shoulder_right",
            "joints": ["spine_shoulder", "shoulder_right", "elbow_right"],
            "min_angle": 0,
            "max_angle": 170
          }
        ],
        "compensations_to_monitor": [
          {
            "id": "trunk_lean",
            "type": "angle_from_vertical",
            "joints": ["spine_base", "spine_shoulder"],
            "max_allowed": 8,
            "feedback_message": "Mantieni la schiena dritta"
          }
        ],
        "phases": [
          {
            "id": "p1",
            "type": "hold",
            "description": "string",
            "targets": [{"joint_id": "shoulder_right", "min": 0, "max": 20}],
            "hold_seconds": 2.0
          }
        ]
      }
    ]
  }
}
```
Evento di valutazione (Python -> n8n)
json
```
{
  "action": "evaluate_step",
  "session_id": "string",
  "exercise_id": "string",
  "exercise_name": "string",
  "exercise_index": 0,
  "exercise_total": 2,
  "phase_id": "p1",
  "phase_type": "hold",
  "phase_description": "string",
  "metrics": {"shoulder_right": 25.3, "trunk_lean": 4.1},
  "targets_to_check": [{"id": "shoulder_right", "min": 0, "max": 20}],
  "compensations_to_check": [{"id": "trunk_lean", "max_allowed": 8}],
  "posture": "in_piedi",
  "required_posture": "in_piedi",
  "history": [ ... ],
  "program_name": "string"
}
```
Risposta di valutazione (n8n -> Python)
json
```
{
  "feedback": "string"
}
```
Richiesta di pianificazione (Python -> n8n)
json
```
{
  "action": "request_plan",
  "session_id": "string",
  "program": { ... },
  "exercise_index": 0,
  "exercise_total": 2,
  "exercise_id": "string",
  "exercise_name": "string",
  "phase_id": "p1",
  "phase_type": "hold",
  "current_targets": {"min": 0, "max": 20, "hold_seconds": 2.0, "reps": null},
  "recent_metrics": {"shoulder_right": 25.3},
  "posture": "in_piedi",
  "required_posture": "in_piedi",
  "history": [ ... ]
}
```
Risposta di pianificazione (n8n -> Python)
json
```
{
  "plan_delta": {
    "adjust_target": {"joint_id": "shoulder_right", "new_min": 0, "new_max": 30},
    "adjust_hold_seconds": null,
    "adjust_reps": null,
    "suggest_skip": false,
    "note": "string"
  }
}
```
Richiesta di report (Python -> n8n)
json
```
{
  "action": "generate_report",
  "session_id": "string",
  "program_name": "string",
  "program_description": "string",
  "exercise_total": 2,
  "exercises_completed": 2,
  "duration_seconds": 340,
  "context": [
    {
      "exercise_id": "ex_1",
      "exercise_name": "string",
      "target_repetitions": 3,
      "reps_completate": 3,
      "phases_completed": 4,
      "phases_skipped": 0,
      "phases_adattate_dal_planner": 1,
      "errors": ["trunk_lean"]
    }
  ]
}
```
Risposta di report (n8n -> Python)
json
```
{
  "report": "string"
}
```
13. Logging e output

debug.log
Contiene tutto l'output del programma: messaggi di stato, log delle chiamate HTTP, errori, traceback. Sovrascritto ad ogni avvio.

reports/session-<timestamp>.txt
Contiene, per ogni sessione completata:

    ID sessione

    nome programma

    numero esercizi completati sul totale

    report narrativo generato dal Reporter

    program_context completo in formato JSON

Terminale
Durante la sessione mostra:

    programma generato con istruzioni

    avanzamento esercizi e fasi

    feedback AI ricevuti

    ricezione di plan_delta

    eventi di gesto

    eccezioni con traceback

    riepilogo finale

14. Costi operativi

Costo hardware iniziale

    PC Windows: 300-450 euro

    Kinect V2: 40-70 euro

    Adattatore: 30-40 euro

    Cavi: 10-20 euro
    Totale: 380-580 euro

Costo software

    Python: gratuito

    OpenCV: gratuito

    n8n Community Edition: gratuito

    Docker Desktop per uso personale: gratuito

Costo API DeepSeek
Stimato in circa 0,015 dollari per sessione completa. Il calcolo si basa su:

    una chiamata al Program Designer (v4-pro)

    una chiamata al Critic (v4-pro)

    circa 13 chiamate medie tra Orchestratore, Coach e Planner su una sessione di 10 ripetizioni

    una chiamata al Reporter
    Le tariffe DeepSeek applicate sono quelle della fascia off-peak, con caching attivo.

Costo energia elettrica
Ipotizzando 60-100 W complessivi per PC e sensore, 8 ore di utilizzo al giorno, 0,27 euro/kWh: 49-79 euro l'anno.
15. Privacy e sicurezza

Nessun dato visivo lascia il PC
Il sistema non invia immagini RGB o mappe di profondità ai servizi AI. Le uniche informazioni trasmesse sono:

    la diagnosi scritta in linguaggio naturale (inviata al Program Designer per la generazione)

    i valori numerici degli angoli articolari

    i valori numerici delle compensazioni

    la history delle ultime fasi (metadati strutturati)

Nessun dato identificativo
Il payload inviato agli agenti non contiene nome, età, codice fiscale o altri dati personali del paziente. Contiene solo session_id (timestamp) e identificativi anonimi degli esercizi.

Conservazione locale
I report sono salvati in locale nel filesystem. Non vengono trasmessi a servizi esterni. Non vengono conservati video o audio.

Human-in-the-loop
Il sistema non decide mai autonomamente di iniziare una sessione o di modificare il programma senza conferma dell'utente. Il paziente approva il programma prima dell'inizio, e può chiedere modifiche.

Nessuna autonomia clinica
Il sistema non è un dispositivo medico. Non formula diagnosi. Non sostituisce il fisioterapista. Le raccomandazioni generate dagli agenti AI sono validate internamente da un Critic, ma restano soggette alla supervisione del professionista sanitario.

16. Limitazioni note

Latenza del feedback AI
Il feedback locale è istantaneo (calcolato in Python a ogni frame). Il feedback AI ha una latenza di 2-4 secondi, dovuta al tempo di inferenza dei modelli linguistici. Non è ottimizzabile senza cambiare architettura o modello.

Nessuna memoria cross-sessione
Il sistema non conserva un profilo del paziente tra sessioni. Ogni sessione riparte da zero. È una scelta di semplicità per il prototipo, non un limite tecnico.

Un solo target per il conteggio
Nei esercizi bilaterali, il conteggio delle ripetizioni è effettuato sul primo target dichiarato. Il secondo lato è monitorato per compensazioni ma non contribuisce al conteggio.

Classificazione della postura euristica
La distinzione tra seduto, in piedi e le altre posture è basata su soglie euristiche su angoli e distanze. Può sbagliare in casi limite (divano con gambe distese, sgabelli alti).

Nessuna validazione clinica
Il sistema è un prototipo tecnologico. Non è stato testato su pazienti reali né validato clinicamente. Non è un dispositivo medico.

Calibrazione soggetta a fallimenti
Se il range misurato durante la calibrazione è inferiore a 20 gradi, la calibrazione viene rifiutata e l'utente deve ripetere il movimento. È il comportamento corretto, ma può richiedere più tentativi se l'utente non capisce cosa deve fare.

Giunti del Kinect V2
Il sensore traccia 25 giunti del corpo, ma non le singole dita né i punti di appoggio dei piedi. Il sistema opera quindi su articolazioni principali (spalle, gomiti, anche, ginocchia, caviglie, colonna) e non su articolazioni fini.

## 17. Scelta del sensore e alternative future

### Perché il Kinect V2

La scelta del sensore Microsoft Kinect V2 non è stata casuale. È il risultato di un compromesso tra costo, disponibilità, maturità dell'ecosistema software e adeguatezza tecnica per il dominio riabilitativo.

**Costo contenuto.** Un Kinect V2 usato sul mercato dell'usato costa tra 40 e 70 euro. L'adattatore USB 3.0 per PC aggiunge altri 30-40 euro. Per un prototipo che deve essere accessibile a piccoli studi di fisioterapia, questa è una soglia di ingresso estremamente bassa. Sensori di profondità più moderni (Azure Kinect DK, Orbbec Femto, Intel RealSense) costano da tre a dieci volte tanto.

**Disponibilità dell'hardware.** Nonostante la produzione sia cessata, il Kinect V2 è ancora ampiamente disponibile nel mercato secondario. Esistono migliaia di unità funzionanti provenienti da dismissioni domestiche e commerciali. Questo rende il prototipo replicabile oggi senza dipendere da fornitori attivi.

**Maturità dell'SDK.** Il Kinect for Windows SDK 2.0 è un SDK maturo, stabile e documentato. Fornisce il tracciamento di 25 giunti dello scheletro a 30 FPS, con precisione millimetrica nella misura degli angoli articolari. Per la riabilitazione, che lavora su range articolari di ampiezza significativa (decine di gradi), questa precisione è più che sufficiente.

**Assenza di marcatori.** Il Kinect V2 funziona senza marcatori fisici sul corpo del paziente. Questo è un requisito importante in ambito riabilitativo: il paziente non deve indossare nulla di scomodo, e la sessione può iniziare in pochi secondi.

**Privacy by design.** Il Kinect V2 produce una mappa di profondità e uno scheletro, ma il sistema non invia mai immagini a servizi esterni. L'elaborazione avviene interamente in locale. Questo è coerente con i requisiti di privacy descritti nella sezione 15.

### Il limite della fine produzione

Microsoft ha annunciato la discontinuità del Kinect V2 nel 2017 e ha cessato la produzione. L'SDK ufficiale non riceve più aggiornamenti. Questo significa che, in un uso clinico reale, non è possibile fare affidamento sul supporto ufficiale a lungo termine.

Tuttavia, la comunità open source ha sviluppato driver alternativi che permettono di continuare a usare l'hardware senza dipendere dall'SDK Microsoft. Il più maturo e diffuso è **libfreenect2**.

### libfreenect2 come alternativa open source

`libfreenect2` è un driver open source per Kinect V2, sviluppato dal progetto OpenKinect. È cross-platform (Windows, Linux, macOS) e permette di accedere a tutti i flussi del sensore: colore, profondità, infrarossi, e tracciamento dello scheletro.

La caratteristica che lo rende particolarmente adatto come sostituto dell'SDK ufficiale è la compatibilità: `libfreenect2` può essere compilato e utilizzato anche senza l'SDK Microsoft installato, ma se l'SDK è presente ne sfrutta le librerie per il tracking dello scheletro. In altre parole, è un'alternativa open source che non richiede di riscrivere il codice applicativo: le API di alto livello per ottenere i giunti sono le stesse.

Il repository di riferimento è `https://github.com/OpenKinect/libfreenect2`. La documentazione ufficiale specifica che il driver supporta esclusivamente Kinect V2 (non Kinect V1 o Xbox 360) e che non è necessario installare l'SDK Microsoft per compilarlo, anche se averlo installato non interferisce.

### Altre alternative possibili

Se in futuro si volesse passare a un sensore ancora in produzione, le alternative principali sono:

- **Azure Kinect DK**: successore ufficiale del Kinect V2, con SDK open source e tracciamento scheletrico migliorato. Costa intorno ai 400 euro.
- **Orbbec Femto Bolt / Mega**: sensori di profondità compatibili con l'SDK Azure Kinect, con costo inferiore.
- **Intel RealSense D455**: sensore di profondità con SDK open source, ampiamente usato in robotica e riabilitazione, ma con un campo di vista più stretto.

Il sistema Kinect Rehab Coach è progettato per essere indipendente dal sensore a livello di logica applicativa: il modulo `analisi_angoli.py` e il modulo `stato_step.py` lavorano su coordinate 3D e nomi di giunti, non su API specifiche del Kinect. Sostituire il sensore richiederebbe di adattare il layer di acquisizione (`main_kinect.py`) e il mapper delle coordinate, ma non la logica di calcolo, di calibrazione o di orchestrazione agentica.

Progetto sviluppato per bioERGOtech — Agentic AI High School Innovation Program
Anno scolastico 2026/2027

Il progetto è distribuito con finalità educative. Non è un dispositivo medico. Non sostituisce il parere di un professionista sanitario.
