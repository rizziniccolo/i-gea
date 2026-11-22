import copy
import time
from dataclasses import dataclass, field
from typing import Optional

from n8n_client import HistoryBuffer
from stato_step import (
    crea_handler,
    StepResult,
    tipi_supportati,
)


@dataclass
class EsercizioResult:
    stato: str
    completato: bool
    messaggio: str
    phase_result: Optional[StepResult] = None
    progresso_esercizio: float = 0.0
    errori_calibrazione: list = field(default_factory=list)
    da_ricalibrare: bool = False


class EsercizioHandler:

    SOGLIA_GESTO_OK_FRAME = 5
    MIN_CAMPIONI_CALIBRAZIONE = 15
    RANGE_MINIMO_CALIBRAZIONE = 20.0
    MARGINE_CLAMP = 0.05
    STALL_TIMEOUT_SECONDI = 15.0
    MAX_PLAN_REQUESTS_PER_PHASE = 2
    CALIB_INIZIO_SOGLIA = 5
    COUNTDOWN_SECONDI = 3.0
    MIN_TARGET_WIDTH = 10.0

    def __init__(self, config, session_id, program_name, exercise_index, exercise_total, program_dict=None):
        self.config = config
        self.id = config.get("id", "ex_1")
        self.name = config.get("exercise_name", "Esercizio")
        self.instructions = config.get("patient_instructions", "")
        self.required_posture = config.get("required_posture")
        self.target_joints = config.get("target_joints", [])
        self.compensations = config.get("compensations_to_monitor", [])
        self.phases_config = config.get("phases", [])
        self._original_phases_config = copy.deepcopy(self.phases_config)

        # FIX: target_repetitions per il ciclo di ripetizioni a livello esercizio
        self.target_repetitions = self._compute_target_repetitions(config)
        self.reps_completate = 0

        self.session_id = session_id
        self.program_name = program_name
        self.exercise_index = exercise_index
        self.exercise_total = exercise_total
        self.program_dict = program_dict or {}

        self.stato = "ISTRUZIONI"

        self.angoli_calib = {tj["id"]: [] for tj in self.target_joints if isinstance(tj, dict) and tj.get("id")}
        self.compensazioni_calib = {}
        self.soglie_calibrate = {}
        self.baseline_compensazioni = {}
        self._messaggio_calib_errore = ""
        self._countdown_start = None

        self.phase_index = 0
        self.current_handler = None
        self.history = HistoryBuffer(maxlen=5)
        self.phase_completate = []
        self._current_targets_to_check = []
        self._current_phase_started_at = None
        self._last_progress = 0.0
        self._last_progress_time = None
        self._last_plan_request_phase = -1
        self._plan_requests_this_phase = 0
        self._last_reps_sent = 0

        self._errori_visti_nella_fase = set()
        self._fase_adattata_dal_planner = False
        self._target_originali_fase = {}

        self._compensations_to_check = [
            {"id": c.get("id", f"comp_{i}"), "max_allowed": c.get("max_allowed")}
            for i, c in enumerate(self.compensations)
            if isinstance(c, dict) and c.get("max_allowed") is not None
        ]

        self.on_step_complete = None
        self.on_plan_request = None

        self._config_error = self._valida_config()

    # ------------------------------------------------------------------

    def _compute_target_repetitions(self, config):
        """
        Determina quante volte ripetere l'intera sequenza di fasi.

        Casi:
        - Se c'è UNA sola fase di tipo "reps": le ripetizioni sono gestite
          internamente alla fase, quindi target_repetitions = 1.
        - Altrimenti: usa config.get("target_repetitions", 1).
        - Valori invalidi (< 1) → 1.
        """
        phases = config.get("phases", [])
        if len(phases) == 1 and isinstance(phases[0], dict) and phases[0].get("type") == "reps":
            return 1
        val = config.get("target_repetitions", 1)
        try:
            val = int(val)
        except (TypeError, ValueError):
            val = 1
        return max(1, val)

    def _valida_config(self):
        if not self.phases_config:
            return "Esercizio senza fasi"
        for ph in self.phases_config:
            if ph.get("type") not in tipi_supportati():
                return f"Fase {ph.get('id', '?')} tipo sconosciuto: {ph.get('type')}"
        return None

    def _exercise_targets_map(self):
        mappa = {}
        for tj in self.target_joints:
            if not isinstance(tj, dict):
                continue
            tid = tj.get("id")
            if tid is None:
                continue
            min_v = tj.get("min_angle")
            max_v = tj.get("max_angle")
            if min_v is not None or max_v is not None:
                mappa[tid] = {"min": min_v, "max": max_v}
        for ph in self.phases_config:
            for t in ph.get("targets", []):
                if not isinstance(t, dict):
                    continue
                tid = t.get("joint_id")
                if tid is None:
                    continue
                if "min" in t or "max" in t:
                    mappa.setdefault(tid, {"min": t.get("min"), "max": t.get("max")})
                elif "to_range" in t:
                    tr = t["to_range"]
                    mappa.setdefault(tid, {"min": tr[0] if tr else None, "max": tr[1] if len(tr) > 1 else None})
        return mappa

    def _snapshot_targets_fase(self, ph_config):
        snap = {}
        for t in ph_config.get("targets", []):
            if not isinstance(t, dict):
                continue
            jid = t.get("joint_id")
            if not jid:
                continue
            snap[jid] = {
                "min": t.get("min"),
                "max": t.get("max"),
                "to_range": list(t["to_range"]) if "to_range" in t and t["to_range"] else None,
            }
        return snap

    # ------------------------------------------------------------------

    def update(self, metriche, compensazioni_attuali, postura):
        if self._config_error:
            return EsercizioResult(
                stato="ERRORE",
                completato=True,
                messaggio=f"Configurazione non valida: {self._config_error}",
            )

        if self.stato == "ISTRUZIONI":
            return EsercizioResult(
                stato="ISTRUZIONI",
                completato=False,
                messaggio="Premi SPAZIO per iniziare la calibrazione",
            )

        if self.stato == "COUNTDOWN":
            return self._update_countdown()

        if self.stato == "CALIBRAZIONE":
            return self._update_calibrazione(metriche)

        if self.stato == "ESECUZIONE":
            return self._update_esecuzione(metriche, compensazioni_attuali, postura)

        return EsercizioResult(
            stato="COMPLETATO",
            completato=True,
            messaggio="Esercizio completato",
            progresso_esercizio=1.0,
        )

    # ------------------------------------------------------------------
    # COUNTDOWN
    # ------------------------------------------------------------------

    def _update_countdown(self):
        elapsed = time.time() - self._countdown_start
        if elapsed >= self.COUNTDOWN_SECONDI:
            self.stato = "CALIBRAZIONE"
            self._reset_calibrazione()
            self._messaggio_calib_errore = ""
            print(f"[ESERCIZIO] Countdown terminato. Calibrazione attiva per {self.name}")
            return self._update_calibrazione({})

        cd = self._get_countdown_info()
        rimanente_int = int(cd["rimanente"]) + 1 if cd["rimanente"] > 0 else 0
        return EsercizioResult(
            stato="COUNTDOWN",
            completato=False,
            messaggio=f"Preparati... {rimanente_int}",
        )

    def _get_countdown_info(self):
        if self.stato != "COUNTDOWN" or self._countdown_start is None:
            return None
        elapsed = time.time() - self._countdown_start
        rimanente = max(0.0, self.COUNTDOWN_SECONDI - elapsed)
        numero = int(rimanente) + 1 if rimanente > 0 else 0
        return {
            "rimanente": rimanente,
            "totale": self.COUNTDOWN_SECONDI,
            "numero": numero,
            "progresso": min(1.0, elapsed / self.COUNTDOWN_SECONDI),
        }

    # ------------------------------------------------------------------
    # PREVIEW DATA
    # ------------------------------------------------------------------

    def get_preview_data(self):
        if self.phase_index >= len(self.phases_config):
            return None
        ph = self.phases_config[self.phase_index]
        ph_type = ph.get("type", "")
        targets = ph.get("targets", [])
        if not targets:
            return None
        t = targets[0]
        if not isinstance(t, dict):
            return None
        joint_id = t.get("joint_id")
        if not joint_id:
            return None

        vertex = joint_id
        for tj in self.target_joints:
            if isinstance(tj, dict) and tj.get("id") == joint_id:
                joints = tj.get("joints", [])
                if len(joints) >= 2:
                    vertex = joints[1]
                break

        return {
            "joint_id": joint_id,
            "vertex": vertex,
            "phase_type": ph_type,
            "min": t.get("min"),
            "max": t.get("max"),
            "to_range": t.get("to_range"),
            "from_range": t.get("from_range"),
        }

    # ------------------------------------------------------------------
    # CALIBRAZIONE
    # ------------------------------------------------------------------

    def _get_calibration_info(self):
        primo_tid = next(iter(self.angoli_calib), None)
        base = {
            "samples": 0,
            "samples_target": self.MIN_CAMPIONI_CALIBRAZIONE,
            "range": 0.0,
            "range_target": self.RANGE_MINIMO_CALIBRAZIONE,
            "error": None,
            "detail": "",
        }

        if not primo_tid:
            base.update({
                "state": "errore",
                "msg": "Nessun target configurato",
                "detail": "Configurazione non valida",
                "error": "Nessun target configurato",
            })
            return base

        campioni = self.angoli_calib[primo_tid]
        n = len(campioni)
        rng = (max(campioni) - min(campioni)) if campioni else 0.0
        base["samples"] = n
        base["range"] = rng

        if self._messaggio_calib_errore:
            base.update({
                "state": "errore",
                "msg": self._messaggio_calib_errore,
                "detail": "Premi SPAZIO per riprovare, oppure [C] per ricominciare",
                "error": self._messaggio_calib_errore,
            })
            return base

        if n < self.CALIB_INIZIO_SOGLIA:
            base.update({
                "state": "inizio",
                "msg": "Calibrazione avviata!",
                "detail": "Esegui il movimento dell'esercizio 2 volte, lentamente e ampiamente",
            })
            return base

        if n < self.MIN_CAMPIONI_CALIBRAZIONE:
            base.update({
                "state": "raccolta",
                "msg": f"Raccolta dati ({n}/{self.MIN_CAMPIONI_CALIBRAZIONE})",
                "detail": "Continua a muoverti normalmente, sto imparando il tuo range",
            })
            return base

        if rng < self.RANGE_MINIMO_CALIBRAZIONE:
            base.update({
                "state": "range_piccolo",
                "msg": f"Range piccolo ({rng:.0f}°)",
                "detail": f"Muoviti più ampio: servono almeno {self.RANGE_MINIMO_CALIBRAZIONE:.0f}°",
            })
            return base

        base.update({
            "state": "pronto",
            "msg": "Pronto per confermare!",
            "detail": "Premi SPAZIO per iniziare l'esercizio",
        })
        return base

    def _update_calibrazione(self, metriche):
        for tid in self.angoli_calib.keys():
            v = metriche.get(tid)
            if v is not None:
                self.angoli_calib[tid].append(v)

        comp_ids = {c.get("id") for c in self.compensations if isinstance(c, dict) and c.get("id")}
        for cid, val in metriche.items():
            if cid in comp_ids:
                self.compensazioni_calib.setdefault(cid, []).append(val)

        cal = self._get_calibration_info()
        return EsercizioResult(
            stato="CALIBRAZIONE",
            completato=False,
            messaggio=cal["msg"],
            errori_calibrazione=[],
        )

    def conferma_calibrazione(self):
        if self.stato != "CALIBRAZIONE":
            return False, "Non in calibrazione"

        primo_tid = next(iter(self.angoli_calib), None)
        if primo_tid is None:
            return False, "Nessun target configurato"

        campioni = self.angoli_calib[primo_tid]
        if len(campioni) < self.MIN_CAMPIONI_CALIBRAZIONE:
            self._messaggio_calib_errore = "Pochi campioni. Fai una ripetizione più lenta e ampia."
            self._reset_calibrazione()
            return False, self._messaggio_calib_errore

        rng = max(campioni) - min(campioni)
        if rng < self.RANGE_MINIMO_CALIBRAZIONE:
            self._messaggio_calib_errore = f"Range troppo piccolo ({rng:.0f}°). Fai un movimento più ampio."
            self._reset_calibrazione()
            return False, self._messaggio_calib_errore

        for tid, valori in self.angoli_calib.items():
            if not valori:
                continue
            lo, hi = min(valori), max(valori)
            marg = (hi - lo) * 0.10
            self.soglie_calibrate[tid] = {"min": lo + marg, "max": hi - marg}

        self._clamp_targets_to_calibration()

        for cid, valori in self.compensazioni_calib.items():
            campioni_c = valori[:15]
            if campioni_c:
                self.baseline_compensazioni[cid] = sum(campioni_c) / len(campioni_c)

        self.stato = "ESECUZIONE"
        self.reps_completate = 0
        self._messaggio_calib_errore = ""
        self._start_phase(0)
        return True, "Calibrazione completata"

    def _reset_calibrazione(self):
        for tid in self.angoli_calib:
            self.angoli_calib[tid] = []
        self.compensazioni_calib = {}

    def _clamp_range(self, r_min, r_max, lo_cal, hi_cal, lo_bound, hi_bound):
        if r_min is None and r_max is None:
            return None, None
        if r_min is None:
            return lo_bound, min(r_max, hi_bound)
        if r_max is None:
            return max(r_min, lo_bound), hi_bound

        width_target = max(self.MIN_TARGET_WIDTH, r_max - r_min)

        if r_min > hi_cal:
            return hi_cal - width_target, hi_cal
        if r_max < lo_cal:
            return lo_cal, lo_cal + width_target

        new_min = max(r_min, lo_bound)
        new_max = min(r_max, hi_bound)

        if new_min >= new_max:
            center = (r_min + r_max) / 2
            cal_center = (lo_cal + hi_cal) / 2
            if center > cal_center:
                new_min = hi_cal - width_target
                new_max = hi_cal
            else:
                new_min = lo_cal
                new_max = lo_cal + width_target

        new_min = max(lo_cal, min(new_min, hi_cal - self.MIN_TARGET_WIDTH))
        new_max = min(hi_cal, max(new_max, lo_cal + self.MIN_TARGET_WIDTH))

        return new_min, new_max

    def _clamp_targets_to_calibration(self):
        for ph in self.phases_config:
            for t in ph.get("targets", []):
                if not isinstance(t, dict):
                    continue
                tid = t.get("joint_id")
                soglia = self.soglie_calibrate.get(tid)
                if soglia is None:
                    continue
                lo_cal, hi_cal = soglia["min"], soglia["max"]
                margine = (hi_cal - lo_cal) * self.MARGINE_CLAMP
                lo_bound = lo_cal + margine
                hi_bound = hi_cal - margine
                if lo_bound >= hi_bound:
                    lo_bound, hi_bound = lo_cal, hi_cal

                if t.get("min") is not None or t.get("max") is not None:
                    new_min, new_max = self._clamp_range(
                        t.get("min"), t.get("max"), lo_cal, hi_cal, lo_bound, hi_bound
                    )
                    if new_min is not None:
                        t["min"] = new_min
                    if new_max is not None:
                        t["max"] = new_max

                if "to_range" in t and isinstance(t["to_range"], (list, tuple)) and len(t["to_range"]) >= 2:
                    tr_min, tr_max = t["to_range"][0], t["to_range"][1]
                    new_min, new_max = self._clamp_range(
                        tr_min, tr_max, lo_cal, hi_cal, lo_bound, hi_bound
                    )
                    t["to_range"] = [new_min, new_max]

                if "from_range" in t and isinstance(t["from_range"], (list, tuple)) and len(t["from_range"]) >= 2:
                    fr_min, fr_max = t["from_range"][0], t["from_range"][1]
                    new_min, new_max = self._clamp_range(
                        fr_min, fr_max, lo_cal, hi_cal, lo_bound, hi_bound
                    )
                    t["from_range"] = [new_min, new_max]

    def restart_calibration(self):
        if self.stato not in ("CALIBRAZIONE", "ESECUZIONE", "COUNTDOWN"):
            return False
        for tid in self.angoli_calib:
            self.angoli_calib[tid] = []
        self.compensazioni_calib = {}
        self.soglie_calibrate = {}
        self.baseline_compensazioni = {}
        self._messaggio_calib_errore = ""
        self.phases_config = copy.deepcopy(self._original_phases_config)
        self.phase_index = 0
        self.current_handler = None
        self.phase_completate = []
        self._current_targets_to_check = []
        self._last_reps_sent = 0
        self._plan_requests_this_phase = 0
        self._last_progress = 0.0
        self._last_progress_time = None
        self._last_plan_request_phase = -1
        self._errori_visti_nella_fase = set()
        self._fase_adattata_dal_planner = False
        self._target_originali_fase = {}
        self.reps_completate = 0
        self.history.clear()
        self.stato = "COUNTDOWN"
        self._countdown_start = time.time()
        print(f"[ESERCIZIO] Riavvio calibrazione (countdown 3s) per {self.name}")
        return True

    # ------------------------------------------------------------------
    # ESECUZIONE
    # ------------------------------------------------------------------

    def _start_phase(self, index):
        self.phase_index = index
        if index >= len(self.phases_config):
            self.stato = "COMPLETATO"
            self.current_handler = None
            self._current_targets_to_check = []
            self._plan_requests_this_phase = 0
            self._last_reps_sent = 0
            return

        ph_config = self.phases_config[index]
        targets_map = self._exercise_targets_map()
        self.current_handler = crea_handler(ph_config, exercise_targets=targets_map)
        if self.current_handler is None:
            print(f"[ESERCIZIO] Tipo fase sconosciuto: {ph_config.get('type')}, salto")
            self._start_phase(index + 1)
            return

        self._current_targets_to_check = self.current_handler.get_targets_to_check()
        self._current_phase_started_at = time.time()
        self._last_progress = 0.0
        self._last_progress_time = time.time()
        self._plan_requests_this_phase = 0
        self._last_reps_sent = 0

        self._errori_visti_nella_fase = set()
        self._fase_adattata_dal_planner = False
        self._target_originali_fase = self._snapshot_targets_fase(ph_config)

        rep_str = ""
        if self.target_repetitions > 1:
            rep_str = f" [Rip {self.reps_completate + 1}/{self.target_repetitions}]"
        print(f"[ESERCIZIO] Fase {index + 1}/{len(self.phases_config)}{rep_str}: "
              f"{ph_config.get('type')} ({ph_config.get('id', '?')})")

        if index > 0 and self.on_plan_request and index != self._last_plan_request_phase:
            self._request_plan()
            self._last_plan_request_phase = index

    def _update_esecuzione(self, metriche, compensazioni_attuali, postura):
        if self.current_handler is None or self.phase_index >= len(self.phases_config):
            self.stato = "COMPLETATO"
            return EsercizioResult(
                stato="COMPLETATO", completato=True,
                messaggio="Esercizio completato", progresso_esercizio=1.0,
            )

        errori_comp = []
        for comp in self.compensations:
            if not isinstance(comp, dict):
                continue
            cid = comp.get("id")
            if not cid:
                continue
            valore = compensazioni_attuali.get(cid)
            limite = comp.get("max_allowed")
            if valore is not None and limite is not None and valore > limite:
                errori_comp.append({
                    "id": cid, "value": valore,
                    "message": comp.get("feedback_message", cid),
                })
                self._errori_visti_nella_fase.add(cid)

        try:
            result = self.current_handler.update(metriche, errori_comp)
        except Exception as e:
            print(f"[ESERCIZIO] Errore handler fase {self.phase_index}: {e}")
            result = StepResult(completato=True, messaggio_ui="Errore fase: salto", errori=errori_comp)

        reps_done = 0
        if result.summary and isinstance(result.summary, dict):
            reps_done = result.summary.get("reps_done", 0) or 0
        if reps_done > self._last_reps_sent:
            self._last_reps_sent = reps_done
            ph_config = self.phases_config[self.phase_index]
            rep_packet = self._build_step_packet(ph_config, metriche)
            rep_packet["action"] = "evaluate_rep"
            rep_packet["rep_number"] = reps_done
            if hasattr(self.current_handler, "repetitions"):
                rep_packet["rep_total"] = self.current_handler.repetitions
            if self.on_step_complete:
                try:
                    self.on_step_complete(rep_packet)
                except Exception as e:
                    print(f"[ESERCIZIO] Errore callback rep: {e}")

        if result.progresso > self._last_progress:
            self._last_progress = result.progresso
            self._last_progress_time = time.time()
        elif self._last_progress_time is not None:
            stallo = time.time() - self._last_progress_time
            if (stallo > self.STALL_TIMEOUT_SECONDI
                    and self.on_plan_request
                    and self._plan_requests_this_phase < self.MAX_PLAN_REQUESTS_PER_PHASE):
                self._request_plan()
                self._plan_requests_this_phase += 1
                self._last_progress_time = time.time()

        # Progresso complessivo: include ciclo ripetizioni
        fasi_totali = len(self.phases_config) * self.target_repetitions
        fasi_fatte_globali = (
            self.reps_completate * len(self.phases_config)
            + self.phase_index + result.progresso
        )
        progresso_esercizio = fasi_fatte_globali / max(1, fasi_totali)

        if result.completato:
            self._completa_fase(metriche, errori_comp)
            fasi_fatte_globali = (
                self.reps_completate * len(self.phases_config) + self.phase_index
            )
            progresso_esercizio = fasi_fatte_globali / max(1, fasi_totali)

        return EsercizioResult(
            stato="ESECUZIONE",
            completato=(self.stato == "COMPLETATO"),
            messaggio=result.messaggio_ui,
            phase_result=result,
            progresso_esercizio=progresso_esercizio,
        )

    def _completa_fase(self, metriche, errori_comp):
        ph_config = self.phases_config[self.phase_index]

        self.history.add(
            exercise_id=self.id,
            phase_id=ph_config.get("id", "?"),
            phase_type=ph_config.get("type", "?"),
            metrics={k: round(v, 1) for k, v in metriche.items() if isinstance(v, (int, float))},
            errors=[e["id"] for e in errori_comp],
        )

        if self.on_step_complete:
            packet = self._build_step_packet(ph_config, metriche)
            try:
                self.on_step_complete(packet)
            except Exception as e:
                print(f"[ESERCIZIO] Errore callback step: {e}")

        entry = {
            "phase_id": ph_config.get("id"),
            "phase_type": ph_config.get("type"),
            "errors": sorted(self._errori_visti_nella_fase),
            "rep_number": self.reps_completate + 1,
        }
        if self._fase_adattata_dal_planner:
            entry["adattata_dal_planner"] = True
            entry["target_originali"] = self._target_originali_fase
            entry["target_effettivi"] = self._snapshot_targets_fase(ph_config)

        self.phase_completate.append(entry)

        rep_str = ""
        if self.target_repetitions > 1:
            rep_str = f" [Rip {self.reps_completate + 1}/{self.target_repetitions}]"
        print(f"[ESERCIZIO] Fase {self.phase_index + 1}{rep_str} completata "
              f"(errori visti: {entry['errors'] or 'nessuno'}"
              f"{', adattata' if self._fase_adattata_dal_planner else ''})")

        # FIX ciclo ripetizioni
        next_phase = self.phase_index + 1
        if next_phase >= len(self.phases_config):
            self.reps_completate += 1
            if self.reps_completate >= self.target_repetitions:
                print(f"[ESERCIZIO] Tutte le {self.target_repetitions} ripetizioni completate. Esercizio finito.")
                self.stato = "COMPLETATO"
                self.current_handler = None
                self._current_targets_to_check = []
                return
            else:
                print(f"[ESERCIZIO] Ciclo {self.reps_completate}/{self.target_repetitions} completato. Ricomincio dalla fase 1.")
                self._start_phase(0)
                return
        else:
            self._start_phase(next_phase)

    def skip_phase(self):
        if self.stato != "ESECUZIONE":
            return False
        if self.phase_index >= len(self.phases_config):
            return False
        print(f"[ESERCIZIO] Skip manuale fase {self.phase_index + 1}")
        self.phase_completate.append({
            "phase_id": self.phases_config[self.phase_index].get("id"),
            "phase_type": self.phases_config[self.phase_index].get("type"),
            "skipped": True,
            "errors": sorted(self._errori_visti_nella_fase),
            "rep_number": self.reps_completate + 1,
        })

        next_phase = self.phase_index + 1
        if next_phase >= len(self.phases_config):
            self.reps_completate += 1
            if self.reps_completate >= self.target_repetitions:
                self.stato = "COMPLETATO"
                self.current_handler = None
                self._current_targets_to_check = []
                return True
            self._start_phase(0)
        else:
            self._start_phase(next_phase)
        return True

    def apply_plan_delta(self, delta):
        if not delta or self.current_handler is None:
            return False
        modificato = False
        ph = self.phases_config[self.phase_index]

        adjust = delta.get("adjust_target")
        if isinstance(adjust, dict):
            jid = adjust.get("joint_id")
            new_min = adjust.get("new_min")
            new_max = adjust.get("new_max")
            if jid and (new_min is not None or new_max is not None):
                for t in ph.get("targets", []):
                    if t.get("joint_id") == jid:
                        if new_min is not None:
                            t["min"] = float(new_min)
                        if new_max is not None:
                            t["max"] = float(new_max)
                        if hasattr(self.current_handler, "targets"):
                            for ht in self.current_handler.targets:
                                if ht.get("joint_id") == jid:
                                    if new_min is not None:
                                        ht["min"] = float(new_min)
                                    if new_max is not None:
                                        ht["max"] = float(new_max)
                                    if "to_range" in ht:
                                        tr = list(ht["to_range"])
                                        if new_min is not None:
                                            tr[0] = float(new_min)
                                        if new_max is not None and len(tr) > 1:
                                            tr[1] = float(new_max)
                                        ht["to_range"] = tr
                                        if hasattr(self.current_handler, "to_range"):
                                            self.current_handler.to_range = tr
                                    modificato = True
                                    break
                        print(f"[PLANNER] Target {jid} → {new_min}-{new_max}")
                        break

        hold = delta.get("adjust_hold_seconds")
        if isinstance(hold, (int, float)) and hold > 0 and ph.get("type") == "hold":
            ph["hold_seconds"] = float(hold)
            if hasattr(self.current_handler, "hold_seconds"):
                self.current_handler.hold_seconds = float(hold)
            modificato = True
            print(f"[PLANNER] Hold → {hold}s")

        reps = delta.get("adjust_reps")
        if isinstance(reps, int) and reps > 0 and ph.get("type") == "reps":
            ph["repetitions"] = reps
            if hasattr(self.current_handler, "repetitions"):
                self.current_handler.repetitions = reps
            modificato = True
            print(f"[PLANNER] Reps → {reps}")

        if modificato:
            self._fase_adattata_dal_planner = True

        if delta.get("suggest_skip"):
            print("[PLANNER] Suggerito skip della fase")
            self.skip_phase()
            modificato = True

        return modificato

    def conferma_inizio(self):
        if self.stato != "ISTRUZIONI":
            return False
        self.stato = "COUNTDOWN"
        self._countdown_start = time.time()
        print(f"[ESERCIZIO] Countdown avviato per {self.name} "
              f"({self.target_repetitions} ripetizioni previste)")
        return True

    def _build_step_packet(self, ph_config, metriche):
        return {
            "action": "evaluate_step",
            "session_id": self.session_id,
            "exercise_id": self.id,
            "exercise_name": self.name,
            "exercise_index": self.exercise_index,
            "exercise_total": self.exercise_total,
            "phase_id": ph_config.get("id", "?"),
            "phase_type": ph_config.get("type", "?"),
            "phase_description": ph_config.get("description", ""),
            "metrics": {k: round(v, 1) for k, v in metriche.items() if isinstance(v, (int, float))},
            "targets_to_check": self._current_targets_to_check,
            "compensations_to_check": self._compensations_to_check,
            "posture": None,
            "required_posture": self.required_posture,
            "history": self.history.snapshot(),
            "program_name": self.program_name,
        }

    def _request_plan(self):
        if self.current_handler is None:
            return
        ph_config = self.phases_config[self.phase_index]
        recent_metrics = {}
        if self.history.snapshot():
            recent_metrics = self.history.snapshot()[-1].get("metrics", {})
        packet = {
            "action": "request_plan",
            "session_id": self.session_id,
            "program": self.program_dict,
            "exercise_index": self.exercise_index,
            "exercise_total": self.exercise_total,
            "exercise_id": self.id,
            "exercise_name": self.name,
            "phase_id": ph_config.get("id", "?"),
            "phase_type": ph_config.get("type", "?"),
            "current_targets": self._current_targets_for_plan(ph_config),
            "recent_metrics": recent_metrics,
            "posture": None,
            "required_posture": self.required_posture,
            "history": self.history.snapshot(),
        }
        try:
            self.on_plan_request(packet)
        except Exception as e:
            print(f"[ESERCIZIO] Errore callback plan: {e}")

    def _current_targets_for_plan(self, ph_config):
        out = {"min": None, "max": None, "hold_seconds": None, "reps": None}
        for t in ph_config.get("targets", []):
            if "min" in t:
                out["min"] = t["min"]
            if "max" in t:
                out["max"] = t["max"]
            if "to_range" in t and t["to_range"]:
                out["min"] = t["to_range"][0]
                out["max"] = t["to_range"][1] if len(t["to_range"]) > 1 else None
        if "hold_seconds" in ph_config:
            out["hold_seconds"] = ph_config["hold_seconds"]
        if "repetitions" in ph_config:
            out["reps"] = ph_config["repetitions"]
        return out

    def get_rendering_info(self):
        ph_config = self.phases_config[self.phase_index] if (
            self.phase_index < len(self.phases_config)
        ) else None

        fasi = []
        for i, ph in enumerate(self.phases_config):
            if i < self.phase_index:
                stato = "completata"
            elif i == self.phase_index and self.stato == "ESECUZIONE":
                stato = "corrente"
            else:
                stato = "futura"
            fasi.append({
                "index": i,
                "id": ph.get("id"),
                "type": ph.get("type"),
                "description": ph.get("description", ""),
                "stato": stato,
            })

        # Progresso complessivo include ciclo ripetizioni
        fasi_totali = len(self.phases_config) * self.target_repetitions
        fasi_fatte = self.reps_completate * len(self.phases_config) + self.phase_index
        if self.stato == "COMPLETATO":
            progresso = 1.0
        elif self.stato == "ESECUZIONE":
            progresso = fasi_fatte / max(1, fasi_totali)
        else:
            progresso = 0.0

        return {
            "stato": self.stato,
            "exercise_name": self.name,
            "exercise_instructions": self.instructions,
            "exercise_index": self.exercise_index,
            "exercise_total": self.exercise_total,
            "phase_index": self.phase_index,
            "phase_total": len(self.phases_config),
            "phase_type": ph_config.get("type") if ph_config else None,
            "fasi": fasi,
            "progresso_esercizio": progresso,
            "soglie_calibrate": self.soglie_calibrate,
            "baseline_compensazioni": self.baseline_compensazioni,
            "preview_data": self.get_preview_data(),
            "calibration": self._get_calibration_info() if self.stato == "CALIBRAZIONE" else None,
            "countdown": self._get_countdown_info(),
            "reps_completate": self.reps_completate,
            "target_repetitions": self.target_repetitions,
        }