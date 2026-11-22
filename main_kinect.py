import os
os.environ["OPENCV_VIDEOIO_PRIORITY_MSMF"] = "0"
import cv2
import time
import sys
import traceback
import atexit

# --- Logging robusto: tutto su file, sempre ---
_log_file = open("debug.log", "w", encoding="utf-8", buffering=1)

class Tee:
    def __init__(self, *streams):
        self.streams = streams
    def write(self, data):
        for s in self.streams:
            try:
                s.write(data)
                s.flush()
            except Exception:
                pass
    def flush(self):
        for s in self.streams:
            try:
                s.flush()
            except Exception:
                pass

sys.stdout = Tee(sys.__stdout__, _log_file)
sys.stderr = Tee(sys.__stderr__, _log_file)

def _log_uncaught(exc_type, exc_value, exc_tb):
    print("\n" + "=" * 60, file=sys.stderr)
    print("UNCAUGHT EXCEPTION", file=sys.stderr)
    print("=" * 60, file=sys.stderr)
    traceback.print_exception(exc_type, exc_value, exc_tb, file=sys.stderr)
    _log_file.flush()

sys.excepthook = _log_uncaught
atexit.register(_log_file.close)

from kinect_next import KinectSensor, StreamType, draw_all_skeletons
from analisi_angoli import (
    angolo_tra_giunti,
    valore_compensazione,
    articolazioni_tracciate,
    giunti_richiesti_da_ricetta,
    classifica_postura,
)
from sessione_programma import SessioneProgramma
from render_step import render_sessione
from tts_manager import TTSManager


# ---------------------------------------------------------------------------
# COSTANTI
# ---------------------------------------------------------------------------

TIMEOUT_ATTESA_PROGRAMMA = 180
MAX_ERRORI_RIPETUTI = 20
SOGLIA_MESSAGGIO_TRACKING = 3   # frame di debounce SOLO per il messaggio visivo
RENDER_SKELETON_GRACE = 5   # 0.17s: solo rendering visivo, non processing

# ---------------------------------------------------------------------------
# FASE PRE-KINECT
# ---------------------------------------------------------------------------

def _attendi(sessione, stati_target, timeout):
    t0 = time.time()
    print("Elaborazione", end="", flush=True)
    while sessione.stato not in stati_target:
        if time.time() - t0 > timeout:
            print(f"\n[ERRORE] Timeout attesa programma ({timeout}s)")
            return False
        time.sleep(0.4)
        print(".", end="", flush=True)
    print()
    return True


def acquisisci_programma(session_id, tts=None):
    print("=" * 60)
    diagnosi = input("Inserisci la diagnosi o il trattamento richiesto:\n> ").strip()
    if not diagnosi:
        print("Nessuna diagnosi inserita. Uscita.")
        return None

    sessione = SessioneProgramma(session_id=session_id, tts=tts)
    sessione.richiedi_programma(diagnosi)

    if not _attendi(sessione, {"IN_ATTESA_CHIARIMENTI", "PROGRAMMA_PRONTO",
                                "ERRORE_GENERAZIONE"}, TIMEOUT_ATTESA_PROGRAMMA):
        return None

    if sessione.stato == "IN_ATTESA_CHIARIMENTI":
        domande = sessione.domande_pendenti
        print(f"\nL'AI ha bisogno di {len(domande)} chiarimenti:")
        risposte = []
        for i, dom in enumerate(domande, 1):
            print(f"\n  {i}. {dom}")
            risposta = input("  Risposta: ").strip()
            risposte.append(risposta if risposta else "Non so")

        sessione.rispondi_chiarimenti(risposte)

        if not _attendi(sessione, {"PROGRAMMA_PRONTO", "ERRORE_GENERAZIONE"},
                         TIMEOUT_ATTESA_PROGRAMMA):
            return None

    if sessione.stato == "ERRORE_GENERAZIONE":
        print(f"\n[ERRORE] Generazione fallita: {sessione.errore}")
        return None

    if sessione.stato != "PROGRAMMA_PRONTO":
        print(f"\n[ERRORE] Stato inatteso: {sessione.stato}")
        return None

    prog = sessione.programma
    print("\n" + "=" * 60)
    print(f"PROGRAMMA: {prog.get('program_name', '')}")
    print(f"{prog.get('program_description', '')}")
    print("-" * 60)
    for i, ex in enumerate(prog.get("steps", []), 1):
        n_ph = len(ex.get("phases", []))
        print(f"  {i}. {ex.get('exercise_name', '')} ({n_ph} fasi)")
        instr = ex.get("patient_instructions", "").strip()
        if instr:
            print(f"     {instr}")
    print("=" * 60)
    print("\nNella finestra Kinect vedrai il programma e le opzioni:")
    print("  [SPAZIO] inizia   [R] chiedi modifiche all'AI   [ESC] esci")
    print()

    return sessione


# ---------------------------------------------------------------------------
# LOOP KINECT
# ---------------------------------------------------------------------------

def _calcola_metriche(joints, esercizio):
    metriche = {}
    for tj in esercizio.target_joints:
        if not isinstance(tj, dict):
            continue
        tj_id = tj.get("id")
        if not tj_id:
            continue
        val = angolo_tra_giunti(joints, tj.get("joints", []))
        if val is not None:
            metriche[tj_id] = val

    for comp in esercizio.compensations:
        if not isinstance(comp, dict):
            continue
        cid = comp.get("id")
        if not cid:
            continue
        val = valore_compensazione(joints, comp)
        if val is not None:
            metriche[cid] = val

    return metriche


def _calcola_compensazioni(joints, esercizio, baseline):
    out = {}
    for comp in esercizio.compensations:
        if not isinstance(comp, dict):
            continue
        cid = comp.get("id")
        if not cid:
            continue
        val = valore_compensazione(joints, comp)
        if val is None:
            continue
        base = baseline.get(cid, val)
        out[cid] = round(abs(val - base), 1)
    return out


def esegui_programma(sessione, tts=None):
    cv2.namedWindow("Kinect - Riabilitazione", cv2.WINDOW_AUTOSIZE)

    ultimo_id_esercizio = None
    giunti_richiesti_cache = set()
    postura = "sconosciuta"
    _report_richiesto_localmente = False
    frame_tracking_ko = 0
    frame_count = 0
    last_fully_tracked_body = None
    last_fully_tracked_frame = -100

    ultimo_errore_msg = ""
    errori_ripetuti = 0

    streams = StreamType.COLOR | StreamType.BODY
    with KinectSensor(streams=streams) as kinect:
        for frames in kinect.poll_frames():
            display = None
            frame_count += 1
            try:
                if frames.color is None:
                    continue

                display = frames.color.as_bgr().copy()

                body = None
                for b in frames.bodies:
                    if getattr(b, "is_tracked", False):
                        body = b
                        break

                es = sessione.esercizio_corrente
                joints = body.joints if body is not None else None

                if es is not None and ultimo_id_esercizio != es.id:
                    giunti_richiesti_cache = giunti_richiesti_da_ricetta(es.config)
                    ultimo_id_esercizio = es.id
                    print(f"[MAIN] Giunti richiesti ({es.name}): {sorted(giunti_richiesti_cache)}")
                    last_fully_tracked_body = None
                    last_fully_tracked_frame = -100

                # Determina processa e motivo dell'eventuale KO
                processa = False
                motivo_ko = None
                if body is None:
                    motivo_ko = "Nessun corpo tracciato"
                elif sessione.stato == "ESERCIZIO_CORRENTE" and \
                        not articolazioni_tracciate(joints, giunti_richiesti_cache):
                    motivo_ko = "Articolazioni non tracciate"
                else:
                    processa = True

                # Aggiorna cache body per rendering skeleton
                if processa and body is not None:
                    last_fully_tracked_body = body
                    last_fully_tracked_frame = frame_count

                # Scegli il body da disegnare: SOLO per rendering visivo, mai per processing
                if body is not None and processa:
                    bodies_to_draw = frames.bodies
                elif last_fully_tracked_body is not None and \
                        (frame_count - last_fully_tracked_frame) <= RENDER_SKELETON_GRACE:
                    bodies_to_draw = [last_fully_tracked_body]
                else:
                    bodies_to_draw = frames.bodies

                draw_all_skeletons(display, bodies_to_draw, kinect.mapper, target_space="color")

                if processa:
                    frame_tracking_ko = 0
                else:
                    frame_tracking_ko += 1

                # --- Rendering + update in base allo stato ---
                if sessione.stato == "PROGRAMMA_PRONTO":
                    info = sessione.get_rendering_info()
                    display = render_sessione(display, info)

                elif sessione.stato == "PROGRAMMA_COMPLETATO":
                    if not _report_richiesto_localmente:
                        print("[MAIN] Programma completato! Richiedo report narrativo...")
                        sessione.richiedi_report()
                        _report_richiesto_localmente = True
                    info = sessione.get_rendering_info()
                    display = render_sessione(display, info)

                elif sessione.stato == "ERRORE_GENERAZIONE":
                    info = sessione.get_rendering_info()
                    display = render_sessione(display, info)

                elif sessione.stato == "ESERCIZIO_CORRENTE":
                    if es is None:
                        info = sessione.get_rendering_info()
                        display = render_sessione(display, info, postura, False)
                    elif not processa:
                        # Messaggio dopo SOLO 3 frame di debounce, sistema già in pausa
                        if frame_tracking_ko >= SOGLIA_MESSAGGIO_TRACKING and motivo_ko:
                            cv2.putText(display, motivo_ko,
                                        (30, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
                        info = sessione.get_rendering_info()
                        display = render_sessione(display, info, postura, False)
                    else:
                        try:
                            postura = classifica_postura(joints)
                        except Exception:
                            postura = "sconosciuta"

                        metriche = _calcola_metriche(joints, es)
                        compensazioni = _calcola_compensazioni(joints, es, es.baseline_compensazioni)

                        result = sessione.update(metriche, compensazioni, postura)

                        if result.get("evento") == "esercizio_completato":
                            print(f"[MAIN] {result.get('messaggio', 'Esercizio completato')}")
                            ultimo_id_esercizio = None
                            postura = "sconosciuta"

                        if sessione.is_programma_completato():
                            print("[MAIN] Programma completato!")

                        info = sessione.get_rendering_info()
                        info["esercizio_result"] = result.get("esercizio_result")
                        info["metriche_correnti"] = metriche
                        required_posture = es.required_posture
                        errore_postura = bool(
                            required_posture
                            and postura not in ("sconosciuta", required_posture)
                        )
                        display = render_sessione(display, info, postura, errore_postura)
                else:
                    info = sessione.get_rendering_info()
                    display = render_sessione(display, info)

                cv2.imshow("Kinect - Riabilitazione", cv2.resize(display, (1280, 720)))
                key = cv2.waitKey(30) & 0xFF

                if key != 255 and key != -1:
                    if key == 27:
                        print("[MAIN] Uscita richiesta (ESC)")
                        return
                    elif key in (ord('n'), ord('N')):
                        st = sessione.stato
                        es_stato = sessione.esercizio_corrente.stato if sessione.esercizio_corrente else "None"
                        ok = sessione.skip_phase()
                        print(f"[MAIN] N → skip_phase={ok} (sessione.stato={st}, es.stato={es_stato})")
                        if ok:
                            ultimo_id_esercizio = None
                    elif key == 32:
                        if sessione.stato == "PROGRAMMA_PRONTO":
                            if sessione.conferma_inizio_programma():
                                print("[MAIN] Programma avviato")
                        elif sessione.stato == "ESERCIZIO_CORRENTE":
                            es_cur = sessione.esercizio_corrente
                            if es_cur and es_cur.stato in ("ISTRUZIONI", "CALIBRAZIONE"):
                                ok, msg = sessione.conferma_avanti()
                                print(f"[MAIN] SPAZIO → conferma_avanti={ok} ({msg})")
                    elif key in (ord('r'), ord('R')):
                        if sessione.stato == "PROGRAMMA_PRONTO":
                            if sessione.puo_richiedere_revisione():
                                cv2.putText(display,
                                            "Scrivi la modifica nel terminale...",
                                            (40, display.shape[0] - 40),
                                            cv2.FONT_HERSHEY_SIMPLEX, 0.7,
                                            (0, 165, 255), 2)
                                cv2.imshow("Kinect - Riabilitazione",
                                           cv2.resize(display, (1280, 720)))
                                cv2.waitKey(100)
                                print("\n[REVISIONE] Descrivi cosa vuoi cambiare (es. 'range troppo ampio', 'preferisco seduto'):")
                                nota = input("> ").strip()
                                if nota:
                                    ok, msg = sessione.richiedi_revisione(nota)
                                    print(f"[MAIN] Revisione: {msg}")
                                else:
                                    print("[MAIN] Revisione annullata (nota vuota)")
                            else:
                                print("[MAIN] Limite revisioni raggiunto o non disponibile")
                    elif key in (ord('c'), ord('C')):
                        ok = sessione.restart_calibration()
                        print(f"[MAIN] C → restart_calibration={ok}")
                        if ok:
                            ultimo_id_esercizio = None
                    elif key in (ord('v'), ord('V')):
                        if tts is not None:
                            nuovo_stato = tts.toggle()
                            print(f"[MAIN] TTS {'attivato' if nuovo_stato else 'disattivato'}")
                    else:
                        if 32 <= key < 127:
                            print(f"[KEY] tasto '{chr(key)}' (code={key}) non gestito")

                errori_ripetuti = 0
                ultimo_errore_msg = ""

            except Exception as e:
                errore_str = f"{type(e).__name__}: {e}"
                if errore_str != ultimo_errore_msg:
                    traceback.print_exc()
                    print(f"[MAIN] Eccezione nel frame: {errore_str}")
                    ultimo_errore_msg = errore_str
                    errori_ripetuti = 1
                else:
                    errori_ripetuti += 1
                    if errori_ripetuti in (5, 10):
                        print(f"[MAIN] Errore ripetuto {errori_ripetuti} volte: {errore_str}")

                if errori_ripetuti >= MAX_ERRORI_RIPETUTI:
                    print(f"[MAIN] Troppi errori consecutivi identici, esco dal loop.")
                    break

                if display is not None:
                    try:
                        cv2.imshow("Kinect - Riabilitazione",
                                   cv2.resize(display, (1280, 720)))
                        if cv2.waitKey(10) & 0xFF == 27:
                            print("[MAIN] Uscita richiesta")
                            return
                    except Exception:
                        pass
                continue

    cv2.destroyAllWindows()


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def main():
    session_start = int(time.time())
    session_id = f"session-{session_start}"
    print(f"[SESSION] ID: {session_id}\n")

    tts = TTSManager(enabled=True)

    try:
        while True:
            sessione = acquisisci_programma(session_id, tts=tts)
            if sessione is not None:
                break
            riprova = input("\nRiprovare la generazione? [s/N]: ").strip().lower()
            if riprova != "s":
                print("Uscita.")
                return

        try:
            esegui_programma(sessione, tts=tts)
        except KeyboardInterrupt:
            print("\n[MAIN] Interrotto da tastiera")
        finally:
            cv2.destroyAllWindows()

        if sessione.is_programma_completato():
            summary = sessione.get_summary_report()
            print("\n" + "=" * 60)
            print("RIEPILOGO SESSIONE")
            print("=" * 60)
            print(f"Programma: {summary['program_name']}")
            print(f"Esercizi completati: {summary['exercises_completed']}/{summary['exercise_total']}")
            for i, ex in enumerate(summary["context"], 1):
                print(f"  {i}. {ex['exercise_name']} - "
                      f"{ex['phases_completed']} fasi OK, "
                      f"{ex['phases_skipped']} saltate, "
                      f"errori: {', '.join(ex['errors']) if ex['errors'] else 'nessuno'}")
            print("=" * 60)
    finally:
        tts.shutdown()


if __name__ == "__main__":
    main()