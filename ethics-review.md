# Ethics Review

##i-Gea Kinect Rehab Coach — Sistema agentico multi-AI per la riabilitazione fisioterapica

Autori: Gamba Benedetta, Rizzi Niccolò, Zuccaretti Chiara

Anno scolastico 2026-2027


---

## Introduzione

Kinect Rehab Coach è un prototipo di sistema che assiste il paziente durante una sessione di riabilitazione fisioterapica. Il sistema riceve una diagnosi scritta in linguaggio naturale, genera un programma di esercizi strutturato, guida il paziente nell'esecuzione tramite un sensore di profondità Kinect V2, rileva le compensazioni posturali in tempo reale, fornisce feedback correttivi e produce un report narrativo finale.

Il sistema è composto da un motore Python che gestisce l'acquisizione dal sensore e il calcolo geometrico, e da un'architettura multi-agente basata su n8n e modelli linguistici DeepSeek che si occupa della generazione del programma, della valutazione contestuale, del feedback empatico e della pianificazione adattiva.

Questa revisione etica analizza il progetto secondo quattro dimensioni: identificazione delle questioni etiche, analisi dei rischi e dei benefici, risposta progettuale, e limitazioni dichiarate onestamente.

La revisione è scritta per essere letta da chi valuta il progetto (giudici della competizione, revisori, potenziali utenti) ma anche da chi in futuro volesse portare il prototipo verso un uso clinico reale. L'obiettivo non è presentare il sistema come privo di problemi, ma esplicitare i problemi che conosciamo e le scelte che abbiamo fatto per affrontarli.

---

## 1. Identification

Il progetto tocca due ambiti ad alto impatto etico: la salute e l'intelligenza artificiale. La combinazione delle due amplifica i rischi di entrambi.

**Questioni etiche sollevate dal progetto**

Il sistema si propone come supporto a un percorso riabilitativo. Questo solleva immediatamente la domanda se un sistema software possa dare indicazioni cliniche senza essere un dispositivo medico validato. La risposta che abbiamo scelto è che il sistema non formula diagnosi e non sostituisce il fisioterapista: propone un programma, il paziente lo approva, il professionista resta il responsabile del percorso. Ma questa distinzione va resa esplicita, perché un utente non esperto potrebbe confondere un suggerimento generato da un'AI con un parere medico.

Il sistema elabora dati relativi al corpo del paziente: posizioni dei giunti, angoli articolari, compensazioni posturali, postura rilevata. Anche se non sono immagini, sono dati biometrici e dati sanitari. La domanda è: chi li vede, dove vengono conservati, per quanto tempo, e come possono essere cancellati.

Il sistema utilizza modelli linguistici esterni (DeepSeek) per generare contenuti. Questo solleva domande sulla trasparenza delle decisioni: perché il sistema ha scelto quel programma? Perché ha proposto quella modifica al target? L'utente può capire il ragionamento o è di fronte a una scatola nera?

Infine, il sistema opera in un contesto di fragilità: il paziente in riabilitazione è una persona che sta recuperando da un trauma, un intervento o una patologia. Un errore del sistema, in questo contesto, ha un peso maggiore rispetto a un errore in un contesto di svago.

**Soggetti coinvolti**

I soggetti direttamente coinvolti sono il paziente che esegue gli esercizi, il fisioterapista che prescrive il percorso, e i familiari o caregiver che assistono il paziente. I soggetti indirettamente coinvolti sono i fornitori dei servizi AI (DeepSeek), i gestori dei dati conservati localmente, e la comunità clinica che potrebbe adottare il sistema in futuro.

---

## 2. Analysis

**Rischi legati all'uso dell'AI in ambito clinico**

Il rischio principale è che l'AI generi un programma clinicamente inappropriato per la specifica condizione del paziente. Un modello linguistico non è un fisioterapista: può produrre range di movimento fisiologicamente implausibili, compensazioni non pertinenti, o istruzioni ambigue. Il sistema mitiga questo rischio con un agente Critic che rivalida la coerenza clinica del programma, e con un validatore strutturale che rifiuta programmi malformati. Ma il Critic è a sua volta un modello linguistico: non è un'oracle clinico.

Un secondo rischio è la deriva del modello nel tempo. Se il modello cambia (aggiornamento di DeepSeek, cambio di fornitore), il comportamento del sistema cambia. Un programma generato oggi potrebbe non essere riproducibile domani. Questa non è una questione teorica: è un problema noto dei sistemi basati su LLM.

Un terzo rischio è la latenza. Il feedback locale è istantaneo, ma il feedback AI arriva con 2-4 secondi di ritardo. In un contesto in cui il paziente sta eseguendo un movimento, un feedback in ritardo può essere fuorviante o irrilevante. Il sistema mitiga mostrando sempre il feedback locale in tempo reale e usando il feedback AI solo come commento contestuale.

**Rischi legati alla privacy**

Il sistema non invia immagini ai servizi AI. Le uniche informazioni trasmesse sono la diagnosi scritta in linguaggio naturale e i valori numerici degli angoli e delle compensazioni. La diagnosi può contenere informazioni identificative se l'utente la scrive in modo dettagliato (per esempio "Mario Rossi, 45 anni, operato al ginocchio destro il 12 marzo"). Il sistema non impedisce questo, ma non lo richiede e non lo incoraggia.

I report generati sono salvati in locale su disco, in chiaro. In un uso reale servirebbe cifratura a riposo e un periodo di conservazione definito.

**Rischi legati all'equità**

Il sistema usa solo giunti 3D, non immagini RGB. Questo riduce drasticamente il rischio di bias demografico: il sistema non può discriminare in base a colore della pelle, abbigliamento, aspetto. Rimane però un possibile bias legato alla corporatura: persone con corporature molto diverse dalla media potrebbero avere un tracking meno preciso. Il sistema mitiga con la calibrazione personalizzata, che misura il range reale di ogni utente invece di usare valori teorici.

Un altro aspetto di equità è economica: il costo hardware (380-580 euro per PC e sensore) e il costo operativo (circa 0,015 dollari per sessione) sono accessibili a piccoli studi di fisioterapia. Il sistema non richiede abbonamenti mensili né infrastrutture cloud proprie.

**Benefici attesi**

Il beneficio principale è la possibilità di offrire al paziente un supporto guidato anche al di fuori delle sedute supervisionate. Un fisioterapista segue tipicamente 2-3 sedute a settimana; il paziente ha bisogno di esercitarsi ogni giorno. Il sistema colma questo divario fornendo guida visiva, correzione posturale e feedback contestuale anche quando il professionista non è presente.

Un secondo beneficio è la standardizzazione della qualità: il sistema rileva le compensazioni con la stessa soglia ogni volta, senza affaticamento, senza distrazioni.

Un terzo beneficio è la documentazione: ogni sessione produce un report narrativo e un program_context strutturato, che il fisioterapista può leggere per capire cosa è successo tra una seduta e l'altra.

---

## 3. Design Response

Il sistema risponde alle questioni etiche identificate attraverso scelte di design esplicite.

**Trasparenza e human-in-the-loop**

Il paziente vede il programma generato prima dell'inizio della sessione. Può approvarlo, chiedere modifiche in linguaggio naturale, o uscire. Le modifiche vengono inviate al Program Designer insieme al programma precedente, che rigenera. Sono consentiti al massimo due tentativi di revisione. Il sistema non decide mai autonomamente di iniziare una sessione: attende sempre la conferma esplicita del paziente.

Durante l'esecuzione, il feedback AI è etichettato come "AI:" per non essere confuso con un parere medico. Il feedback locale (bordo rosso, messaggio di correzione) è separato e riconoscibile.

**Privacy by design**

Nessuna immagine RGB o mappa di profondità lascia il PC. L'AI riceve solo JSON strutturati con valori numerici. Il payload non contiene nome, età, codice fiscale o altri dati identificativi del paziente. Contiene solo un session_id basato su timestamp e identificativi anonimi degli esercizi.

I report sono salvati in locale, non su cloud. Il sistema non ha memoria persistente cross-sessione, quindi ogni sessione riparte da zero: non c'è un profilo che si accumula nel tempo.

**Deterministico dove serve, AI dove serve**

La scelta architetturale più importante è la separazione tra ciò che è deterministico e ciò che richiede intelligenza. Il calcolo degli angoli, la verifica delle soglie, il conteggio delle ripetizioni sono eseguiti da codice Python e JavaScript. La generazione del programma, il feedback contestuale, la pianificazione adattiva sono delegati ai modelli linguistici.

Questo garantisce che i numeri critici non siano soggetti ad allucinazione: il Valutatore è un nodo JavaScript, non un LLM. Non può "decidere" che 105 gradi è dentro il range 40-150 se non lo è.

**Validazione strutturale e clinica**

Ogni programma passa attraverso due livelli di validazione. Il primo è strutturale: controlla la presenza dei campi obbligatori, il numero corretto di giunti, la coerenza tra fasi e target. Il secondo è clinico: un agente Critic rivalida la plausibilità fisiologica, la pertinenza delle compensazioni, l'assenza di controindicazioni evidenti.

Se la validazione fallisce, il programma non arriva al paziente. Se il Critic propone una correzione, questa viene a sua volta validata strutturalmente prima di essere accettata.

**Calibrazione personalizzata**

I target generati dall'AI sono teorici. Il sistema non li usa direttamente: chiede al paziente di eseguire il movimento per due volte, misura il range reale, e adatta i target al range effettivo. Se un target è irraggiungibile, viene ancorato al limite mantenendo la larghezza originale. Se il range misurato è inferiore a 20 gradi, la calibrazione viene rifiutata e l'utente deve ripetere il movimento.

Questo riduce il rischio di proporre esercizi inappropriati per la mobilità effettiva del paziente.

**Trasparenza del report**

Il report narrativo generato dal Reporter è in linguaggio semplice, non tecnico, e menziona esplicitamente gli errori accumulati durante la sessione. Tutti gli errori visti durante una fase vengono registrati, non solo quelli del frame finale. Il report non nasconde le difficoltà: se il paziente ha compensato, il report lo dice in modo costruttivo.

**Onestà sulle limitazioni**

Il sistema dichiara esplicitamente di non essere un dispositivo medico, di non aver ricevuto validazione clinica, di non sostituire il fisioterapista. Questa dichiarazione è ripetuta nel README e nella presente revisione, ed è visibile all'utente nella schermata di completamento della sessione.

---

## 4. Honest Limitations

Il sistema ha limitazioni che conosciamo e che non nascondiamo.

**Nessuna validazione clinica**

Il sistema non è stato testato su pazienti reali. È un prototipo tecnologico, non un dispositivo medico. Non può essere usato in ambito clinico senza una validazione formale, che richiederebbe studi controllati, approvazione di un comitato etico, e certificazione come dispositivo medico di classe appropriata.

**Nessun consenso informato formale**

Il prototipo non implementa un consenso informato formale. In un uso reale servirebbe un documento scritto che spieghi al paziente come funziona il sistema, quali dati vengono conservati, per quanto tempo, e come possono essere cancellati. Il sistema non ha un meccanismo per raccogliere questo consenso.

**Nessuna cifratura dei dati a riposo**

I report sono salvati in chiaro su disco. In un uso reale servirebbe cifratura a riposo, controllo degli accessi, e un periodo di conservazione definito con cancellazione automatica.

**Nessuna memoria persistente con diritto alla cancellazione**

Il sistema non conserva un profilo del paziente tra sessioni. Questo è un limite per la continuità del percorso riabilitativo, ma anche una semplificazione etica: senza memoria persistente, non c'è un accumulo di dati che richieda un diritto alla cancellazione formalizzato. In futuro, se la memoria persistente verrà implementata, servirà un meccanismo esplicito per il diritto all'oblio.

**Latenza del feedback AI**

Il feedback AI arriva con 2-4 secondi di ritardo. Questo è inerente all'uso di modelli linguistici. Non è ottimizzabile senza cambiare architettura. Il sistema mitiga mostrando il feedback locale in tempo reale, ma il feedback AI resta un commento a posteriori, non una guida in tempo reale.

**Classificazione della postura euristica**

La distinzione tra seduto, in piedi, sdraiato, inginocchiato, accovacciato è basata su soglie euristiche. Può sbagliare in casi limite (divano con gambe distese, sgabelli alti). Il sistema non blocca l'esecuzione se la postura è ambigua, mostra solo un avviso.

**Un solo target per il conteggio**

Nei esercizi bilaterali, il conteggio delle ripetizioni è effettuato su un solo lato. Il secondo lato è monitorato per compensazioni ma non contribuisce al conteggio. Questo significa che un paziente potrebbe completare l'esercizio avendo eseguito meno ripetizioni sul lato debole.

**Dipendenza da servizi esterni**

Il sistema dipende da DeepSeek per le chiamate AI. Se il servizio è irraggiungibile, il sistema degrada: mostra "Sistema offline" e prosegue con il feedback locale. Ma la generazione del programma e il report finale non sono possibili. In un uso clinico reale servirebbe un fallback locale (modelli su piccola scala) o un fornitore alternativo configurato.

**Fine produzione del Kinect V2**

Il Kinect V2 non è più in produzione dal 2017. Il sistema è progettato per funzionare con l'SDK Microsoft, ma in futuro sarà necessario passare a driver open source (libfreenect2) o a sensori più moderni (Azure Kinect DK, Orbbec Femto). Questo è un tema di sostenibilità a lungo termine, non un rischio immediato.

**Nessun audit log formale**

Il sistema produce un file `debug.log` con tutte le chiamate e le risposte degli agenti. Questo è utile per il debug, ma non è un audit log formale nel senso richiesto da normative come il GDPR o l'AI Act. In un uso reale servirebbe un log strutturato, immutabile, con timestamp certificati.

---

## Conclusione

Kinect Rehab Coach è un prototipo tecnologico che affronta un problema reale: la carenza di supervisione quotidiana nella riabilitazione fisioterapica. Il sistema è progettato con scelte etiche esplicite: privacy by design, human-in-the-loop, separazione tra deterministico e intelligente, validazione strutturale e clinica dei contenuti generati dall'AI.

Il sistema non è un dispositivo medico, non è validato clinicamente, e non sostituisce il fisioterapista. Queste non sono dichiarazioni di facciata: sono il presupposto su cui il progetto è costruito. Il valore del prototipo è dimostrare che un'architettura agentica multi-AI può essere progettata in modo responsabile, con limiti chiari e con una separazione netta tra ciò che l'AI può fare e ciò che non deve fare.

Le limitazioni sono dichiarate apertamente perché un sistema che nasconde i propri limiti è più pericoloso di un sistema che li esplicita. La strada verso un uso clinico reale richiede validazione formale, consenso informato, cifratura dei dati, audit log strutturato, e sostenibilità a lungo termine dell'hardware. Il prototipo è un punto di partenza, non un punto di arrivo.
