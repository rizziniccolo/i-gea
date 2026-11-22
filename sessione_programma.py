import json
import os
import time
import threading

from n8n_client import (
    invia_richiesta_programma,
    invia_evento_step,
    invia_piano,
    invia_report,
)
from esercizio import EsercizioHandler, EsercizioResult


REPORTS_DIR = "reports"
MAX_REVISIONI = 2


class SessioneProgramma:
    def __init__(self, session_id, tts=None):
        self.session_id = session_id
        self.tts = tts

        # Stato ciclo di vita
        self.stato = "INIZIALE"

        # Programma
        self.diagnosi = ""
        self.programma = None
        self.programma_indice = 0
        self.esercizio_corrente = None
        self.program_context = []
        self._session_start_time = time.time()

        # Comunicazione AI
        self.ultimo_feedback_ai = "In attesa..."
        self.ultimo_feedback_time = 0.0
        self.errore = None
        self.domande_pendenti = []

        # Report finale
        self.report_finale = None
        self.report_status = "idle"
        self._report_richiesto = False

        # Human-in-the-loop
        self.revisioni_usate = 0
        self._attesa_revisione = False

        # Plan delta pendente
        self._plan_delta_pending = None
        self._plan_delta_target_exercise = None
        self._plan_delta_target_phase = None

        # Thread safety
        self._lock = threading.RLock()

    # ==================================================================
    # GENERAZIONE PROGRAMMA
    # ==================================================================

    def richiedi_programma(self, diagnosi):
        with self._lock:
            self.diagnosi = diagnosi
            self.errore = None
            self.domande_pendenti = []
            self.stato = "IN_ATTESA_PROGRAMMA"

        invia_richiesta_programma(diagnosi=diagnosi, callback=self._on_risposta_programma)

    def rispondi_chiarimenti(self, risposte):
        with self._lock:
            domande = list(self.domande_pendenti)
            self.errore = None
            self.stato = "IN_ATTESA_PROGRAMMA"

        invia_richiesta_programma(
            diagnosi=self.diagnosi,
            answers=risposte,
            previous_questions=domande,
            callback=self._on_risposta_programma,
        )

    def puo_richiedere_revisione(self):
        with self._lock:
            return (self.stato == "PROGRAMMA_PRONTO"
                    and self.revisioni_usate < MAX_REVISIONI
                    and not self._attesa_revisione)

    def richiedi_revisione(self, nota):
        with self._lock:
            if self.stato != "PROGRAMMA_PRONTO":
                return False, "Nessun programma da revisionare"
            if self.revisioni_usate >= MAX_REVISIONI:
                return False, f"Hai raggiunto il limite di {MAX_REVISIONI} revisioni"
            if self.programma is None:
                return False, "Nessun programma in memoria"
            if not nota or not nota.strip():
                return False, "Nota di revisione vuota"

            self.revisioni_usate += 1
            self._attesa_revisione = True
            self.errore = None
            self.stato = "IN_ATTESA_PROGRAMMA"
            programma_corrente = self.programma
            diagnosi = self.diagnosi
            tentativo = self.revisioni_usate

        print(f"[SESSIONE] Revisione {tentativo}/{MAX_REVISIONI}: {nota}")
        invia_richiesta_programma(
            diagnosi=diagnosi,
            revision_note=nota,
            previous_program=programma_corrente,
            callback=self._on_risposta_programma,
        )
        return True, "Richiesta di revisione inviata"

    def _on_risposta_programma(self, data):
        with self._lock:
            if not isinstance(data, dict):
                self.errore = "Risposta non valida"
                self.stato = "ERRORE_GENERAZIONE"
                self._attesa_revisione = False
                return

            if data.get("error"):
                self.errore = data["error"]
                self.stato = "ERRORE_GENERAZIONE"
                self._attesa_revisione = False
                print(f"[SESSIONE] Errore generazione programma: {self.errore}")
                return

            action = data.get("action")

            if action == "clarify":
                self.domande_pendenti = data.get("questions", [])
                self.stato = "IN_ATTESA_CHIARIMENTI"
                self._attesa_revisione = False
                print(f"[SESSIONE] AI chiede {len(self.domande_pendenti)} chiarimenti")
                return

            if action == "generate":
                programma = data.get("program")
                if not programma or not programma.get("steps"):
                    self.errore = "Programma vuoto o malformato"
                    self.stato = "ERRORE_GENERAZIONE"
                    self._attesa_revisione = False
                    return

                self.programma = programma
                self.domande_pendenti = []
                self._attesa_revisione = False

                if data.get("_warning"):
                    print(f"[SESSIONE] ⚠️ Warning dal Critic: {data['_warning']}")
                if data.get("_corrected"):
                    print(f"[SESSIONE] ✅ Programma corretto dal Critic")

                n_ex = len(programma.get("steps", []))
                n_phases_tot = sum(len(ex.get("phases", [])) for ex in programma.get("steps", []))
                print(f"[SESSIONE] Programma generato: {n_ex} esercizi, {n_phases_tot} fasi totali")
                self.stato = "PROGRAMMA_PRONTO"
                return

            self.errore = f"Azione sconosciuta: {action}"
            self.stato = "ERRORE_GENERAZIONE"
            self._attesa_revisione = False

    def retry_generazione(self):
        if self.stato not in ("ERRORE_GENERAZIONE", "IN_ATTESA_CHIARIMENTI"):
            return False
        self.richiedi_programma(self.diagnosi)
        return True

    # ==================================================================
    # INIZIO PROGRAMMA
    # ==================================================================

    def conferma_inizio_programma(self):
        with self._lock:
            if self.stato != "PROGRAMMA_PRONTO":
                return False
            self._session_start_time = time.time()
            self._avvia_esercizio(0)
            return True

    # ==================================================================
    # CICLO ESERCIZI
    # ==================================================================

    def _avvia_esercizio(self, index):
        steps = self.programma.get("steps", []) if self.programma else []
        if index >= len(steps):
            self.stato = "PROGRAMMA_COMPLETATO"
            self.esercizio_corrente = None
            print(f"[SESSIONE] 🎉 Programma completato! {len(self.program_context)} esercizi eseguiti")
            return

        self.programma_indice = index
        config = steps[index]

        es = EsercizioHandler(
            config=config,
            session_id=self.session_id,
            program_name=self.programma.get("program_name", ""),
            exercise_index=index,
            exercise_total=len(steps),
            program_dict=self.programma,
        )
        es.on_step_complete = self._on_step_complete
        es.on_plan_request = self._on_plan_request

        self.esercizio_corrente = es
        self.stato = "ESERCIZIO_CORRENTE"
        self._plan_delta_pending = None

        print(f"[SESSIONE] Avvio esercizio {index + 1}/{len(steps)}: {es.name}")

    def _registra_esercizio_completato(self, es):
        errori_totali = []
        for fase in es.phase_completate:
            errori_totali.extend(fase.get("errors", []))
        visti = set()
        errori_unici = []
        for e in errori_totali:
            if e not in visti:
                visti.add(e)
                errori_unici.append(e)

        fasi_adattate = [p for p in es.phase_completate if p.get("adattata_dal_planner")]

        self.program_context.append({
            "exercise_id": es.id,
            "exercise_name": es.name,
            "target_repetitions": es.target_repetitions,
            "reps_completate": es.reps_completate,
            "phases_completed": len([p for p in es.phase_completate if not p.get("skipped")]),
            "phases_skipped": len([p for p in es.phase_completate if p.get("skipped")]),
            "phases_adattate_dal_planner": len(fasi_adattate),
            "errors": errori_unici,
        })

    # ==================================================================
    # CALLBACK N8N
    # ==================================================================

    def _on_step_complete(self, packet):
        invia_evento_step(packet, callback=self._on_feedback_ricevuto)

    def _on_plan_request(self, packet):
        with self._lock:
            self._plan_delta_target_exercise = packet.get("exercise_id")
            self._plan_delta_target_phase = packet.get("phase_id")
        invia_piano(packet, callback=self._on_plan_ricevuto)

    def _on_feedback_ricevuto(self, data):
        with self._lock:
            if not isinstance(data, dict):
                print(f"[DEBUG] Feedback non-dict: {data}")
                return
            if data.get("error"):
                self.ultimo_feedback_ai = "Sistema offline. Continua con calma."
                print(f"[DEBUG] Feedback errore: {data['error']}")
            else:
                fb = data.get("feedback", "") or str(data)
                self.ultimo_feedback_ai = fb
                self.ultimo_feedback_time = time.time()
                print(f"[FEEDBACK] {fb}")
                if self.tts is not None:
                    self.tts.speak(fb, priority="normal")

    def _on_plan_ricevuto(self, data):
        with self._lock:
            if not isinstance(data, dict) or "plan_delta" not in data:
                return
            self._plan_delta_pending = data["plan_delta"]
            print(f"[SESSIONE] plan_delta ricevuto per fase "
                  f"{self._plan_delta_target_phase}: {data['plan_delta']}")

    # ==================================================================
    # REPORT FINALE
    # ==================================================================

    def richiedi_report(self):
        with self._lock:
            if self._report_richiesto:
                return False
            self._report_richiesto = True
            self.report_status = "loading"

        summary = self.get_summary_report()
        durata = int(time.time() - self._session_start_time)
        summary["duration_seconds"] = durata
        summary["action"] = "generate_report"

        print(f"[SESSIONE] Richiesta report narrativo...")
        invia_report(summary, callback=self._on_report_ricevuto)
        return True

    def _on_report_ricevuto(self, data):
        with self._lock:
            if not isinstance(data, dict):
                self.report_status = "error"
                return
            if data.get("error"):
                self.report_status = "error"
                print(f"[SESSIONE] Errore report: {data['error']}")
                return
            report = data.get("report", "").strip()
            if not report:
                self.report_status = "error"
                return
            self.report_finale = report
            self.report_status = "ready"
            print(f"[REPORT] {report}")
            self._salva_report_su_file(report)
            if self.tts is not None:
                self.tts.speak(report, priority="high")

    def _salva_report_su_file(self, report):
        try:
            os.makedirs(REPORTS_DIR, exist_ok=True)
            path = os.path.join(REPORTS_DIR, f"{self.session_id}.txt")
            summary = self.get_summary_report()
            with open(path, "w", encoding="utf-8") as f:
                f.write(f"Session: {self.session_id}\n")
                f.write(f"Programma: {summary['program_name']}\n")
                f.write(f"Esercizi: {summary['exercises_completed']}/{summary['exercise_total']}\n\n")
                f.write("REPORT:\n")
                f.write(report)
                f.write("\n\nCONTEXT:\n")
                f.write(json.dumps(summary["context"], indent=2, ensure_ascii=False))
            print(f"[REPORT] Salvato in {path}")
        except Exception as e:
            print(f"[REPORT] Errore salvataggio: {e}")

    # ==================================================================
    # UPDATE
    # ==================================================================

    def update(self, metriche, compensazioni, postura):
        with self._lock:
            if self.stato != "ESERCIZIO_CORRENTE":
                return self._stato_non_esecuzione()

            es = self.esercizio_corrente
            if es is None:
                self.stato = "PROGRAMMA_COMPLETATO"
                return self._stato_non_esecuzione()

            if self._plan_delta_pending is not None:
                phase_ok = (
                    self._plan_delta_target_exercise == es.id
                    and self._plan_delta_target_phase == (
                        es.phases_config[es.phase_index].get("id")
                        if es.phase_index < len(es.phases_config)
                        else None
                    )
                )
                if phase_ok:
                    es.apply_plan_delta(self._plan_delta_pending)
                    self._plan_delta_pending = None
                else:
                    print(f"[SESSIONE] plan_delta per fase diversa, scartato")
                    self._plan_delta_pending = None

            result = es.update(metriche, compensazioni, postura)

            if result.completato:
                self._registra_esercizio_completato(es)
                next_index = self.programma_indice + 1
                self._avvia_esercizio(next_index)
                return {
                    "stato": self.stato,
                    "evento": "esercizio_completato",
                    "messaggio": "Esercizio completato!",
                    "programma_completato": self.stato == "PROGRAMMA_COMPLETATO",
                }

            return self._render_result(es, result)

    def _stato_non_esecuzione(self):
        base = {
            "stato": self.stato,
            "evento": None,
            "errore": self.errore,
            "domande_pendenti": list(self.domande_pendenti),
            "ultimo_feedback": self.ultimo_feedback_ai,
            "ultimo_feedback_time": self.ultimo_feedback_time,
            "report_finale": self.report_finale,
            "report_status": self.report_status,
        }
        if self.stato == "PROGRAMMA_COMPLETATO":
            base["evento"] = "programma_completato"
            base["program_context"] = list(self.program_context)
        return base

    def _render_result(self, es, es_result):
        return {
            "stato": "ESERCIZIO_CORRENTE",
            "evento": None,
            "esercizio": es.get_rendering_info(),
            "esercizio_result": {
                "stato": es_result.stato,
                "messaggio": es_result.messaggio,
                "progresso_esercizio": es_result.progresso_esercizio,
                "phase_result": self._phase_result_to_dict(es_result.phase_result),
            },
            "ultimo_feedback": self.ultimo_feedback_ai,
            "ultimo_feedback_time": self.ultimo_feedback_time,
        }

    def _phase_result_to_dict(self, pr):
        if pr is None:
            return None
        return {
            "completato": pr.completato,
            "progresso": pr.progresso,
            "messaggio_ui": pr.messaggio_ui,
            "errori": pr.errori,
        }

    # ==================================================================
    # INPUT UTENTE
    # ==================================================================

    def conferma_avanti(self):
        """
        Conferma l'azione corrente:
          - ISTRUZIONI → COUNTDOWN (poi CALIBRAZIONE automatica)
          - CALIBRAZIONE → ESECUZIONE
        Chiamato dal main quando l'utente preme SPAZIO.
        """
        with self._lock:
            if self.stato != "ESERCIZIO_CORRENTE":
                return False, "Nessun esercizio in corso"
            es = self.esercizio_corrente
            if es is None:
                return False, "Nessun esercizio"

            if es.stato == "ISTRUZIONI":
                if es.conferma_inizio():
                    return True, "Countdown avviato"
                return False, "Impossibile avviare il countdown"

            if es.stato == "CALIBRAZIONE":
                ok, msg = es.conferma_calibrazione()
                if ok:
                    print(f"[SESSIONE] Calibrazione completata.")
                else:
                    print(f"[SESSIONE] Calibrazione fallita: {msg}")
                return ok, msg

            return False, f"Stato esercizio: {es.stato}"

    def skip_phase(self):
        with self._lock:
            if self.stato != "ESERCIZIO_CORRENTE" or self.esercizio_corrente is None:
                return False
            return self.esercizio_corrente.skip_phase()
            
    def restart_calibration(self):
        """Riavvia la calibrazione dell'esercizio corrente."""
        with self._lock:
            if self.stato != "ESERCIZIO_CORRENTE" or self.esercizio_corrente is None:
                return False
            return self.esercizio_corrente.restart_calibration()

    # ==================================================================
    # RENDERING INFO
    # ==================================================================

    def get_rendering_info(self):
        with self._lock:
            info = {
                "stato": self.stato,
                "program_name": self.programma.get("program_name", "") if self.programma else "",
                "program_description": self.programma.get("program_description", "") if self.programma else "",
                "exercise_index": self.programma_indice,
                "exercise_total": len(self.programma.get("steps", [])) if self.programma else 0,
                "ultimo_feedback": self.ultimo_feedback_ai,
                "ultimo_feedback_time": self.ultimo_feedback_time,
                "errore": self.errore,
                "domande_pendenti": list(self.domande_pendenti),
                "esercizi": [],
                "esercizio_corrente": None,
                "program_context": list(self.program_context),
                "report_finale": self.report_finale,
                "report_status": self.report_status,
                "revisioni_usate": self.revisioni_usate,
                "revisioni_max": MAX_REVISIONI,
                "puo_revisionare": self.revisioni_usate < MAX_REVISIONI,
                "tts_enabled": self.tts.is_enabled() if self.tts is not None else False,
            }

            if self.programma:
                for i, ex in enumerate(self.programma.get("steps", [])):
                    if i < self.programma_indice:
                        stato = "completato"
                    elif i == self.programma_indice and self.stato == "ESERCIZIO_CORRENTE":
                        stato = "corrente"
                    else:
                        stato = "futuro"
                    info["esercizi"].append({
                        "index": i,
                        "name": ex.get("exercise_name", ""),
                        "stato": stato,
                        "phase_total": len(ex.get("phases", [])),
                        "instructions": ex.get("patient_instructions", ""),
                    })

                if self.esercizio_corrente:
                    info["esercizio_corrente"] = self.esercizio_corrente.get_rendering_info()

            return info

    # ==================================================================
    # UTILITY
    # ==================================================================

    def is_programma_completato(self):
        with self._lock:
            return self.stato == "PROGRAMMA_COMPLETATO"

    def is_in_esecuzione(self):
        with self._lock:
            return self.stato == "ESERCIZIO_CORRENTE"

    def get_summary_report(self):
        with self._lock:
            return {
                "session_id": self.session_id,
                "program_name": self.programma.get("program_name", "") if self.programma else "",
                "program_description": self.programma.get("program_description", "") if self.programma else "",
                "exercise_total": len(self.programma.get("steps", [])) if self.programma else 0,
                "exercises_completed": len(self.program_context),
                "context": list(self.program_context),
            }