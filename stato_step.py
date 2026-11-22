import time
from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# CONTRATTO COMUNE
# ---------------------------------------------------------------------------

@dataclass
class StepResult:
    """
    Risultato dell'aggiornamento di una fase. È l'unico contratto tra
    gli handler e il resto del sistema (rendering + packet n8n).
    """
    completato: bool = False
    progresso: float = 0.0           # 0.0 - 1.0, per la barra di avanzamento
    messaggio_ui: str = ""           # stringa breve da mostrare nel pannello
    errori: list = field(default_factory=list)  # [{"id","value","message"}]
    summary: dict = field(default_factory=dict) # dati per il packet n8n


class StepHandler:
    """Interfaccia base. Ogni tipo di fase implementa update()."""

    def __init__(self, config):
        self.config = config
        self.id = config.get("id", "phase")
        self.type = config.get("type", "unknown")
        self.description = config.get("description", "")
        self.completato = False
        self._start_time = None

    # --- Da implementare nelle sottoclassi ---

    def update(self, metriche, errori_comp):
        """
        metriche: dict { joint_id: valore_angolo }
        errori_comp: list [{"id","value","message"}] compensazioni oltre soglia
        Ritorna StepResult.
        """
        raise NotImplementedError

    # --- Comuni ---

    def reset(self):
        self.completato = False
        self._start_time = None

    def get_description(self):
        return self.description

    def get_targets_to_check(self):
        """
        Lista di target da passare al Valutatore Deterministico in n8n.
        Formato: [{"id": str, "min": num, "max": num}, ...]
        """
        return []


# ---------------------------------------------------------------------------
# HELPER: valutazione di un target rispetto a un range
# ---------------------------------------------------------------------------

def _target_in_range(valore, min_val, max_val):
    if valore is None:
        return False
    if min_val is not None and valore < min_val:
        return False
    if max_val is not None and valore > max_val:
        return False
    return True


# ---------------------------------------------------------------------------
# HANDLER 1: REPS
# ---------------------------------------------------------------------------

class RepsStep(StepHandler):
    """
    Fase a ripetizioni. L'utente oscilla tra min e max del target.
    Una rep conta ogni volta che si passa da "sotto min" a "sopra max"
    (o viceversa), con isteresi per evitare rimbalzi su rumore.
    """

    def __init__(self, config):
        super().__init__(config)
        self.targets = config.get("targets", [])
        self.repetitions = config.get("repetitions", 10)
        # Stato isteresi per il target principale (il primo)
        self.fase = "rest"   # rest | flexed | extended
        self.reps = 0
        if not self.targets:
            self._errore_config = "RepsStep senza targets"
        else:
            self._errore_config = None

    def reset(self):
        super().reset()
        self.fase = "rest"
        self.reps = 0

    def update(self, metriche, errori_comp):
        if self._errore_config:
            return StepResult(messaggio_ui=f"ERRORE: {self._errore_config}")

        t = self.targets[0]
        jid = t.get("joint_id")
        min_v = t.get("min")
        max_v = t.get("max")

        val = metriche.get(jid)
        if val is None:
            return StepResult(
                messaggio_ui=f"Target {jid} non tracciato",
                errori=errori_comp,
            )

        # Isteresi
        if self.fase == "rest" and min_v is not None and val < min_v:
            self.fase = "flexed"
        elif self.fase == "flexed" and max_v is not None and val > max_v:
            self.fase = "extended"
            self.reps += 1
        elif self.fase == "extended" and min_v is not None and val < min_v:
            self.fase = "flexed"

        self.completato = self.reps >= self.repetitions
        progresso = min(1.0, self.reps / max(1, self.repetitions))

        return StepResult(
            completato=self.completato,
            progresso=progresso,
            messaggio_ui=f"Rep: {self.reps}/{self.repetitions}  (angolo: {val:.0f}°)",
            errori=errori_comp,
            summary={
                "reps_done": self.reps,
                "reps_target": self.repetitions,
            },
        )

    def get_targets_to_check(self):
        if not self.targets:
            return []
        t = self.targets[0]
        return [{
            "id": t.get("joint_id"),
            "min": t.get("min"),
            "max": t.get("max"),
        }]


# ---------------------------------------------------------------------------
# HANDLER 2: HOLD ISOMETRIC
# ---------------------------------------------------------------------------

class HoldIsometricStep(StepHandler):
    """
    Fase di mantenimento statico. Il target deve restare nel range per
    hold_seconds, senza compensazioni attive. Se esce dal range o
    compensa, il timer si resetta.
    """

    def __init__(self, config):
        super().__init__(config)
        self.targets = config.get("targets", [])
        self.hold_seconds = config.get("hold_seconds", 3.0)
        self._hold_start = None
        self._hold_accumulato = 0.0  # secondi accumulati
        self._ultimo_tick = None

    def reset(self):
        super().reset()
        self._hold_start = None
        self._hold_accumulato = 0.0
        self._ultimo_tick = None

    def update(self, metriche, errori_comp):
        ora = time.time()

        # Verifica condizione: tutti i target in range e nessuna compensazione
        tutti_in_range = True
        primo_target_val = None
        for t in self.targets:
            jid = t.get("joint_id")
            val = metriche.get(jid)
            if primo_target_val is None:
                primo_target_val = val
            if not _target_in_range(val, t.get("min"), t.get("max")):
                tutti_in_range = False
                break

        in_posizione = tutti_in_range and not errori_comp

        if in_posizione:
            if self._hold_start is None:
                self._hold_start = ora
            tenuto = ora - self._hold_start
            self.completato = tenuto >= self.hold_seconds
            progresso = min(1.0, tenuto / max(0.001, self.hold_seconds))
            stato_txt = f"Mantieni: {tenuto:.1f}/{self.hold_seconds:.1f}s"
        else:
            self._hold_start = None
            progresso = 0.0
            if errori_comp:
                stato_txt = "Correggi la postura per iniziare il conteggio"
            else:
                stato_txt = f"Raggiungi il target ({primo_target_val:.0f}°)" if primo_target_val is not None else "Attesa target"

        return StepResult(
            completato=self.completato,
            progresso=progresso,
            messaggio_ui=stato_txt,
            errori=errori_comp,
            summary={
                "hold_seconds_target": self.hold_seconds,
                "hold_seconds_elapsed": round(progresso * self.hold_seconds, 1),
                "in_position": in_posizione,
            },
        )

    def get_targets_to_check(self):
        return [{
            "id": t.get("joint_id"),
            "min": t.get("min"),
            "max": t.get("max"),
        } for t in self.targets if t.get("joint_id")]


# ---------------------------------------------------------------------------
# HANDLER 3: MOVEMENT
# ---------------------------------------------------------------------------

class MovementStep(StepHandler):
    """
    Fase di raggiungimento di un target.
    - Se from_range è specificato: prima deve essere in from_range, poi to_range.
    - Se from_range non è specificato: basta che entri in to_range.
    """

    def __init__(self, config):
        super().__init__(config)
        self.targets = config.get("targets", [])
        t = self.targets[0] if self.targets else {}
        self.joint_id = t.get("joint_id")
        self.to_range = t.get("to_range", [None, None])
        self.from_range = t.get("from_range", [None, None])
        self._stato = "attesa"  # attesa | verso_to | completato
        self._from_ok = False

    def reset(self):
        super().reset()
        self._stato = "attesa"
        self._from_ok = False

    def update(self, metriche, errori_comp):
        val = metriche.get(self.joint_id) if self.joint_id else None
        if val is None:
            return StepResult(
                messaggio_ui=f"Target {self.joint_id} non tracciato",
                errori=errori_comp,
            )

        to_min, to_max = self.to_range[0], self.to_range[1]
        from_min, from_max = self.from_range[0], self.from_range[1]

        # Se from_range è specificato, richiedi prima il passaggio per from
        if from_min is not None or from_max is not None:
            if _target_in_range(val, from_min, from_max):
                self._from_ok = True
            if not self._from_ok:
                return StepResult(
                    messaggio_ui=f"Parti da {from_min}-{from_max}° (sei a {val:.0f}°)",
                    errori=errori_comp,
                    summary={"in_target": False, "in_from": False},
                )

        in_target = _target_in_range(val, to_min, to_max)
        if in_target:
            self._stato = "completato"
            self.completato = True

        progresso = 1.0 if self.completato else 0.0
        if in_target:
            msg = f"Target raggiunto: {val:.0f}° (in {to_min}-{to_max})"
        else:
            msg = f"Raggiungi {to_min}-{to_max}° (sei a {val:.0f}°)"

        return StepResult(
            completato=self.completato,
            progresso=progresso,
            messaggio_ui=msg,
            errori=errori_comp,
            summary={
                "in_target": in_target,
                "current_value": round(val, 1),
            },
        )

    def get_targets_to_check(self):
        if not self.joint_id:
            return []
        return [{
            "id": self.joint_id,
            "min": self.to_range[0],
            "max": self.to_range[1],
        }]


# ---------------------------------------------------------------------------
# HANDLER 4: REST
# ---------------------------------------------------------------------------

class RestStep(StepHandler):
    """Pausa. Nessun controllo sui target, solo un timer."""

    def __init__(self, config):
        super().__init__(config)
        self.duration = config.get("duration_seconds", 10)
        self._inizio = None

    def reset(self):
        super().reset()
        self._inizio = None

    def update(self, metriche, errori_comp):
        ora = time.time()
        if self._inizio is None:
            self._inizio = ora
        elapsed = ora - self._inizio
        self.completato = elapsed >= self.duration
        progresso = min(1.0, elapsed / max(0.001, self.duration))
        rimanenti = max(0, self.duration - elapsed)

        return StepResult(
            completato=self.completato,
            progresso=progresso,
            messaggio_ui=f"Pausa: {rimanenti:.0f}s rimanenti",
            errori=[],  # durante il rest non mostriamo correzioni
            summary={
                "rest_elapsed": round(elapsed, 1),
                "rest_target": self.duration,
            },
        )


# ---------------------------------------------------------------------------
# HANDLER 5: CUSTOM RULES
# ---------------------------------------------------------------------------

class CustomRulesStep(StepHandler):
    """
    Fase con regole composizionali. Supporta:
    - completion.all_of / any_of: lista di condizioni
    - completion.min_duration_seconds: le condizioni devono restare vere per N sec

    Condizioni supportate:
    - {"condition": "target_in_range", "target_id": "X"}
      verifica che metriche[target_id] sia nel range del target dell'esercizio
    - {"condition": "reps_completed", "target_id": "X", "count": N}
      contatore isteresi come RepsStep per il target specificato
    """

    def __init__(self, config):
        super().__init__(config)
        completion = config.get("completion", {})
        self.all_of = completion.get("all_of")
        self.any_of = completion.get("any_of")
        self.combinator = "all_of" if self.all_of is not None else (
            "any_of" if self.any_of is not None else None
        )
        self.conditions = self.all_of if self.all_of is not None else self.any_of or []
        self.min_duration = completion.get("min_duration_seconds", 0.0)
        self._hold_start = None
        # Stato reps per target_id
        self._rep_state = {}   # tid -> "rest"|"flexed"|"extended"
        self._rep_count = {}   # tid -> int
        # Target config dell'esercizio (passata dal chiamante via update?
        # No: la passiamo nel config come "exercise_targets" in fase di costruzione)
        self.exercise_targets = config.get("exercise_targets", {})

    def reset(self):
        super().reset()
        self._hold_start = None
        self._rep_state = {}
        self._rep_count = {}

    def _eval_condition(self, cond, metriche):
        tipo = cond.get("condition")
        if tipo == "target_in_range":
            tid = cond.get("target_id")
            t = self.exercise_targets.get(tid, {})
            val = metriche.get(tid)
            return _target_in_range(val, t.get("min"), t.get("max"))
        if tipo == "reps_completed":
            tid = cond.get("target_id")
            target_count = cond.get("count", 1)
            t = self.exercise_targets.get(tid, {})
            min_v, max_v = t.get("min"), t.get("max")
            val = metriche.get(tid)
            if val is None:
                return False
            stato = self._rep_state.get(tid, "rest")
            count = self._rep_count.get(tid, 0)
            if stato == "rest" and min_v is not None and val < min_v:
                self._rep_state[tid] = "flexed"
            elif stato == "flexed" and max_v is not None and val > max_v:
                self._rep_state[tid] = "extended"
                count += 1
                self._rep_count[tid] = count
            elif stato == "extended" and min_v is not None and val < min_v:
                self._rep_state[tid] = "flexed"
            return count >= target_count
        return False

    def update(self, metriche, errori_comp):
        if not self.conditions:
            return StepResult(
                messaggio_ui="ERRORE: custom_rules senza condizioni",
                errori=errori_comp,
            )

        results = [self._eval_condition(c, metriche) for c in self.conditions]
        if self.combinator == "all_of":
            tutte_vere = all(results)
        else:
            tutte_vere = any(results)

        ora = time.time()

        if self.min_duration > 0:
            if tutte_vere:
                if self._hold_start is None:
                    self._hold_start = ora
                tenuto = ora - self._hold_start
                progresso = min(1.0, tenuto / self.min_duration)
                if tenuto >= self.min_duration:
                    self.completato = True
                msg = f"Condizioni soddisfatte: {tenuto:.1f}/{self.min_duration:.1f}s"
            else:
                self._hold_start = None
                progresso = 0.0
                msg = "Soddisfa le condizioni"
        else:
            self.completato = tutte_vere
            progresso = 1.0 if tutte_vere else 0.0
            msg = "Condizioni soddisfatte" if tutte_vere else "Soddisfa le condizioni"

        return StepResult(
            completato=self.completato,
            progresso=progresso,
            messaggio_ui=msg,
            errori=errori_comp,
            summary={
                "conditions_satisfied": results,
                "min_duration_target": self.min_duration,
            },
        )

    def get_targets_to_check(self):
        out = []
        for c in self.conditions:
            if c.get("condition") in ("target_in_range", "reps_completed"):
                tid = c.get("target_id")
                t = self.exercise_targets.get(tid, {})
                out.append({
                    "id": tid,
                    "min": t.get("min"),
                    "max": t.get("max"),
                })
        return out


# ---------------------------------------------------------------------------
# REGISTRY
# ---------------------------------------------------------------------------

STEP_HANDLERS = {
    "reps":            RepsStep,
    "hold":            HoldIsometricStep,
    "movement":        MovementStep,
    "rest":            RestStep,
    "custom_rules":    CustomRulesStep,
}


def crea_handler(phase_config, exercise_targets=None):
    """
    Factory. Restituisce un handler per il tipo di fase indicato, oppure
    None se il tipo non è supportato.

    exercise_targets: dict { target_id: {"min": N, "max": M} }
    Necessario solo per CustomRulesStep, che deve conoscere i range dei target
    dell'esercizio per valutare target_in_range e reps_completed.
    """
    tipo = phase_config.get("type", "reps")
    cls = STEP_HANDLERS.get(tipo)
    if cls is None:
        return None
    # Aggiunge exercise_targets al config per CustomRulesStep
    cfg = dict(phase_config)
    if exercise_targets is not None:
        cfg["exercise_targets"] = exercise_targets
    return cls(cfg)


def tipi_supportati():
    """Per validazione e documentazione."""
    return list(STEP_HANDLERS.keys())