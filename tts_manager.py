import queue
import threading
import time


class TTSManager:
    """
    Gestore TTS con coda prioritaria e rate limiting.

    - Un solo thread worker (pyttsx3 non è thread-safe)
    - Coda FIFO con max 2 elementi "normal" in attesa
    - Elementi "high" (report finale) non vengono mai scartati
    - Rate limit: ignora feedback ravvicinati (< MIN_INTERVAL)
    - Toggle on/off con tasto V
    """

    MAX_QUEUE_SIZE = 2
    MIN_INTERVAL_SECONDI = 2.0

    def __init__(self, enabled=True):
        self._enabled = enabled
        self._queue = queue.Queue()
        self._worker = None
        self._stop_event = threading.Event()
        self._last_speak_time = 0.0
        self._lock = threading.Lock()
        self._engine = None
        self._engine_ready = False

        self._start_worker()

    # ------------------------------------------------------------------
    # API PUBBLICA
    # ------------------------------------------------------------------

    def speak(self, text, priority="normal"):
        """
        Mette in coda un testo da leggere.
        priority: "normal" (feedback AI) | "high" (report finale)
        """
        if not text or not text.strip():
            return
        if not self._enabled:
            return

        testo = text.strip()
        ora = time.time()

        # Rate limit per feedback normal
        if priority == "normal":
            with self._lock:
                if ora - self._last_speak_time < self.MIN_INTERVAL_SECONDI:
                    print(f"[TTS] Skip (rate limit): {testo[:50]}...")
                    return

        # Gestione coda: se piena, scarta il più vecchio (tranne high)
        if self._queue.qsize() >= self.MAX_QUEUE_SIZE and priority == "normal":
            try:
                vecchio = self._queue.get_nowait()
                print(f"[TTS] Scarto vecchio: {vecchio.get('text', '')[:50]}...")
            except queue.Empty:
                pass

        self._queue.put({"text": testo, "priority": priority, "ts": ora})
        print(f"[TTS] In coda ({priority}): {testo[:60]}...")

    def toggle(self):
        """Attiva/disattiva TTS. Ritorna il nuovo stato (bool)."""
        with self._lock:
            self._enabled = not self._enabled
            if not self._enabled:
                # Svuota la coda
                while not self._queue.empty():
                    try:
                        self._queue.get_nowait()
                    except queue.Empty:
                        break
            stato = "ON" if self._enabled else "OFF"
            print(f"[TTS] {stato}")
            return self._enabled

    def is_enabled(self):
        return self._enabled

    def shutdown(self):
        """Ferma il worker. Da chiamare a fine sessione."""
        self._stop_event.set()
        try:
            self._queue.put_nowait(None)  # sentinel
        except queue.Full:
            pass
        if self._worker:
            self._worker.join(timeout=3)
        if self._engine:
            try:
                self._engine.stop()
            except Exception:
                pass

    # ------------------------------------------------------------------
    # WORKER
    # ------------------------------------------------------------------

    def _start_worker(self):
        self._worker = threading.Thread(target=self._run, daemon=True)
        self._worker.start()

    def _run(self):
        """Loop del worker: inizializza pyttsx3 e processa la coda."""
        try:
            import pyttsx3
        except ImportError:
            print("[TTS] pyttsx3 non installato. TTS disabilitato. Esegui: pip install pyttsx3")
            return

        try:
            self._engine = pyttsx3.init()
            # Prova a scegliere una voce italiana
            try:
                voices = self._engine.getProperty("voices")
                italian = [v for v in voices if "it" in (v.id or "").lower() or "ital" in (v.name or "").lower()]
                if italian:
                    self._engine.setProperty("voice", italian[0].id)
                    print(f"[TTS] Voce italiana: {italian[0].name}")
                else:
                    print(f"[TTS] Nessuna voce italiana trovata, uso default")
            except Exception as e:
                print(f"[TTS] Errore selezione voce: {e}")

            self._engine.setProperty("rate", 175)  # velocità (default 200)
            self._engine.setProperty("volume", 0.9)
            self._engine_ready = True
            print("[TTS] Engine pronto")
        except Exception as e:
            print(f"[TTS] Errore inizializzazione: {e}")
            return

        while not self._stop_event.is_set():
            try:
                item = self._queue.get(timeout=0.5)
            except queue.Empty:
                continue

            if item is None:
                break
            if not self._enabled:
                continue

            testo = item.get("text", "")
            if not testo:
                continue

            with self._lock:
                self._last_speak_time = time.time()

            try:
                print(f"[TTS] Leggo: {testo[:70]}...")
                self._engine.say(testo)
                self._engine.runAndWait()
            except Exception as e:
                print(f"[TTS] Errore lettura: {e}")

        print("[TTS] Worker terminato")


# ---------------------------------------------------------------------------
# SINGLETON (opzionale, comodo per demo)
# ---------------------------------------------------------------------------

_instance = None

def get_tts():
    global _instance
    if _instance is None:
        _instance = TTSManager()
    return _instance