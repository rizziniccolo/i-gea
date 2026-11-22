import cv2
import time
from preview_animation import render_preview

# ---------------------------------------------------------------------------
# PALETTE
# ---------------------------------------------------------------------------

COL_VERDE       = (0, 220, 0)
COL_GIALLO      = (0, 255, 255)
COL_ARANCIONE   = (0, 165, 255)
COL_ROSSO       = (0, 0, 220)
COL_GRIGIO      = (180, 180, 180)
COL_GRIGIO_SCURO = (110, 110, 110)
COL_BIANCO      = (255, 255, 255)
COL_BLU         = (255, 180, 50)
COL_PANEL_BG    = (35, 35, 35)
COL_PANEL_BORDER = (90, 90, 90)

FONT = cv2.FONT_HERSHEY_SIMPLEX

BAR_H = 44
LEFT_PANEL_W = 420
FOOTER_H = 110
PADDING = 16


# ---------------------------------------------------------------------------
# UTILITY
# ---------------------------------------------------------------------------

def _panel(display, x, y, w, h, alpha=0.75):
    """Pannello semi-trasparente OTTIMIZZATO: lavora solo sulla ROI, non sull'intera immagine."""
    h_img, w_img = display.shape[:2]
    x1 = max(0, min(int(x), w_img - 1))
    y1 = max(0, min(int(y), h_img - 1))
    x2 = max(x1 + 1, min(int(x + w), w_img))
    y2 = max(y1 + 1, min(int(y + h), h_img))
    if x2 - x1 < 2 or y2 - y1 < 2:
        return

    roi = display[y1:y2, x1:x2]
    overlay = roi.copy()
    cv2.rectangle(overlay, (0, 0), (x2 - x1, y2 - y1), COL_PANEL_BG, -1)
    cv2.addWeighted(overlay, alpha, roi, 1 - alpha, 0, roi)
    cv2.rectangle(display, (x1, y1), (x2, y2), COL_PANEL_BORDER, 1)


def _truncate(text, max_chars):
    if text is None:
        return ""
    text = str(text)
    return text if len(text) <= max_chars else text[:max_chars - 1] + "…"


def _wrap_text(text, max_chars):
    if not text:
        return []
    words = str(text).split()
    lines = []
    cur = ""
    for w in words:
        if not cur:
            cur = w
        elif len(cur) + 1 + len(w) <= max_chars:
            cur += " " + w
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def _icona_stato(stato):
    return {"completato": "OK", "corrente": ">>", "futuro": "  "}.get(stato, "  ")


def _colore_stato(stato):
    return {
        "completato": COL_VERDE,
        "corrente": COL_GIALLO,
        "futuro": COL_GRIGIO_SCURO,
    }.get(stato, COL_GRIGIO_SCURO)


def _finestra_scroll(items, index_corrente, max_visibili):
    n = len(items)
    if n <= max_visibili:
        return 0, n
    start = max(0, index_corrente - max_visibili // 2)
    end = min(n, start + max_visibili)
    start = max(0, end - max_visibili)
    return start, end


# ---------------------------------------------------------------------------
# RENDER PRINCIPALE
# ---------------------------------------------------------------------------

def render_sessione(display, sessione_info, postura=None, errore_postura=False):
    h, w = display.shape[:2]
    stato = sessione_info.get("stato", "SCONOSCIUTO")

    if stato == "IN_ATTESA_PROGRAMMA":
        return _render_attesa(display, "Generazione programma in corso...")
    if stato == "IN_ATTESA_CHIARIMENTI":
        return _render_chiarimenti(display, sessione_info)
    if stato == "PROGRAMMA_PRONTO":
        return _render_programma_pronto(display, sessione_info)
    if stato == "ERRORE_GENERAZIONE":
        return _render_errore(display, sessione_info)
    if stato == "ESERCIZIO_CORRENTE":
        return _render_esercizio(display, sessione_info, postura, errore_postura)
    if stato == "PROGRAMMA_COMPLETATO":
        return _render_completato(display, sessione_info)
    return _render_attesa(display, f"Stato: {stato}")


# ---------------------------------------------------------------------------
# STATI SEMPLICI
# ---------------------------------------------------------------------------

def _render_attesa(display, messaggio):
    h, w = display.shape[:2]
    _panel(display, w // 2 - 380, h // 2 - 60, 760, 120)
    cv2.putText(display, messaggio, (w // 2 - 350, h // 2 + 10),
                FONT, 0.9, COL_GIALLO, 2)
    return display


def _render_errore(display, sessione_info):
    h, w = display.shape[:2]
    msg = sessione_info.get("errore", "Errore sconosciuto")
    _panel(display, w // 2 - 420, h // 2 - 100, 840, 200)
    cv2.putText(display, "ERRORE NELLA GENERAZIONE DEL PROGRAMMA",
                (w // 2 - 390, h // 2 - 50), FONT, 0.9, COL_ROSSO, 2)
    for i, line in enumerate(_wrap_text(msg, 60)):
        cv2.putText(display, line, (w // 2 - 390, h // 2 - 10 + i * 26),
                    FONT, 0.65, COL_BIANCO, 1)
    cv2.putText(display, "Premi R per riprovare, ESC per uscire",
                (w // 2 - 390, h // 2 + 70), FONT, 0.7, COL_GIALLO, 2)
    return display


def _render_chiarimenti(display, sessione_info):
    h, w = display.shape[:2]
    domande = sessione_info.get("domande_pendenti", [])
    _panel(display, 40, 40, w - 80, h - 80)
    cv2.putText(display, "L'AI ha bisogno di alcuni chiarimenti:",
                (70, 90), FONT, 0.95, COL_GIALLO, 2)
    y = 140
    for i, dom in enumerate(domande):
        cv2.putText(display, f"{i + 1}.", (70, y), FONT, 0.75, COL_BLU, 2)
        for line in _wrap_text(dom, 90):
            cv2.putText(display, line, (110, y), FONT, 0.65, COL_BIANCO, 1)
            y += 26
        y += 12
    cv2.putText(display, "Rispondi nel terminale e premi INVIO per continuare",
                (70, h - 80), FONT, 0.7, COL_ARANCIONE, 2)
    return display


def _render_programma_pronto(display, sessione_info):
    h, w = display.shape[:2]
    _panel(display, 40, 40, w - 80, h - 80)

    cv2.putText(display, "PROGRAMMA GENERATO",
                (70, 90), FONT, 1.0, COL_GIALLO, 2)
    cv2.putText(display, _truncate(sessione_info.get("program_name", ""), 80),
                (70, 128), FONT, 0.9, COL_BIANCO, 2)

    desc = sessione_info.get("program_description", "")
    y = 165
    for line in _wrap_text(desc, 110)[:2]:
        cv2.putText(display, line, (70, y), FONT, 0.58, COL_GRIGIO, 1)
        y += 22

    y += 20
    cv2.putText(display, "ESERCIZI:", (70, y), FONT, 0.7, COL_GIALLO, 1)
    y += 30

    esercizi = sessione_info.get("esercizi", [])
    for ex in esercizi:
        if y > h - 150:
            remaining = len(esercizi) - ex["index"]
            cv2.putText(display,
                        f"... e altri {remaining} esercizi (leggi il resto nel terminale)",
                        (70, y), FONT, 0.55, COL_GRIGIO, 1)
            break

        nome = _truncate(ex.get("name", ""), 80)
        n_fasi = ex.get("phase_total", 0)
        cv2.putText(display, f"{ex['index'] + 1}. {nome}  ({n_fasi} fasi)",
                    (70, y), FONT, 0.68, COL_BIANCO, 2)
        y += 24

        istruzioni = ex.get("instructions", "")
        if istruzioni:
            all_righe = _wrap_text(istruzioni, 110)
            for r in all_righe:
                if y > h - 130:
                    cv2.putText(display, "... (testo completo nel terminale)",
                                (90, y), FONT, 0.5, COL_GRIGIO_SCURO, 1)
                    y += 18
                    break
                cv2.putText(display, r, (90, y), FONT, 0.52, COL_GRIGIO, 1)
                y += 20
        y += 10

    y_footer = h - 90
    rev_usate = sessione_info.get("revisioni_usate", 0)
    rev_max = sessione_info.get("revisioni_max", 2)
    puo_rev = sessione_info.get("puo_revisionare", True)

    cv2.putText(display, "OPZIONI:",
                (70, y_footer), FONT, 0.65, COL_GIALLO, 1)
    y_footer += 28
    cv2.putText(display, "[SPAZIO] Conferma e inizia il programma",
                (70, y_footer), FONT, 0.62, COL_VERDE, 2)
    y_footer += 24
    if puo_rev:
        colore_r = COL_ARANCIONE
        testo_r = f"[R] Chiedi modifiche all'AI ({rev_max - rev_usate} tentativi rimasti)"
    else:
        colore_r = COL_GRIGIO_SCURO
        testo_r = f"[R] Esauriti ({rev_usate}/{rev_max} revisioni usate)"
    cv2.putText(display, testo_r, (70, y_footer), FONT, 0.58, colore_r, 1)
    y_footer += 24
    cv2.putText(display, "[ESC] Esci senza iniziare",
                (70, y_footer), FONT, 0.55, COL_GRIGIO_SCURO, 1)

    return display


def _render_completato(display, sessione_info):
    h, w = display.shape[:2]
    _panel(display, 40, 40, w - 80, h - 80)

    cv2.putText(display, "PROGRAMMA COMPLETATO!",
                (70, 100), FONT, 1.4, COL_VERDE, 3)

    context = sessione_info.get("program_context", [])
    n_es = len(context)
    cv2.putText(display, f"Hai completato {n_es} esercizi.",
                (70, 145), FONT, 0.9, COL_BIANCO, 2)

    report_status = sessione_info.get("report_status", "idle")
    report = sessione_info.get("report_finale")
    report_y = 210

    if report_status == "loading":
        dots = "." * (int(time.time() * 2) % 4)
        cv2.putText(display, f"Generazione report narrativo{dots}",
                    (70, report_y), FONT, 0.85, COL_GIALLO, 2)
        cv2.putText(display, "(l'AI sta analizzando la sessione)",
                    (70, report_y + 30), FONT, 0.6, COL_GRIGIO_SCURO, 1)
    elif report_status == "ready" and report:
        cv2.putText(display, "REPORT DELLA SESSIONE:",
                    (70, report_y), FONT, 0.7, COL_GIALLO, 2)
        yy = report_y + 36
        max_chars = int((w - 160) / 11)
        lines = _wrap_text(report, max_chars)[:6]
        for line in lines:
            cv2.putText(display, line, (70, yy),
                        FONT, 0.68, COL_BIANCO, 1)
            yy += 30
    elif report_status == "error":
        cv2.putText(display, "Report narrativo non disponibile.",
                    (70, report_y), FONT, 0.75, COL_ARANCIONE, 2)
        cv2.putText(display, "(i dati della sessione sono stati salvati)",
                    (70, report_y + 30), FONT, 0.6, COL_GRIGIO_SCURO, 1)
    else:
        y = report_y
        for i, ex in enumerate(context[:5]):
            nome = _truncate(ex.get("exercise_name", ""), 60)
            cv2.putText(display, f"  • {nome}",
                        (70, y), FONT, 0.65, COL_BIANCO, 1)
            y += 28
        if n_es > 5:
            cv2.putText(display, f"  ... e altri {n_es - 5}",
                        (70, y), FONT, 0.6, COL_GRIGIO, 1)

    cv2.putText(display, "Premi ESC per uscire.",
                (70, h - 80), FONT, 0.75, COL_GIALLO, 2)

    return display


# ---------------------------------------------------------------------------
# STATO ESERCIZIO CORRENTE
# ---------------------------------------------------------------------------

def _render_esercizio(display, sessione_info, postura, errore_postura):
    h, w = display.shape[:2]

    _render_barra_programma(display, sessione_info, w)

    top = BAR_H + 8
    bottom = h - FOOTER_H
    _render_lista_esercizi(display, sessione_info, PADDING, top,
                           LEFT_PANEL_W, bottom - top)

    right_x = PADDING + LEFT_PANEL_W + 8
    right_w = w - right_x - PADDING
    _render_pannello_esercizio(display, sessione_info, right_x, top,
                               right_w, bottom - top)

    # Preview spostata in BASSO a destra: sopra il footer, dove il braccio alzato non passa
    preview_size = 200
    preview_x = w - preview_size - PADDING
    preview_y = h - FOOTER_H - preview_size - 8
    if preview_y > top + 100:
        render_preview(display, sessione_info, preview_x, preview_y, size=preview_size)

    # Overlay countdown (se attivo)
    es = sessione_info.get("esercizio_corrente")
    if es and es.get("stato") == "COUNTDOWN":
        _render_countdown_overlay(display, es.get("countdown"), h, w)

    _render_footer(display, sessione_info, postura, errore_postura, h, w)

    return display


def _render_barra_programma(display, sessione_info, w):
    ex_idx = sessione_info.get("exercise_index", 0)
    ex_tot = max(1, sessione_info.get("exercise_total", 1))

    # Ottimizzato: lavora solo sulla fascia alta (BAR_H)
    h_img = display.shape[0]
    y2 = min(BAR_H, h_img)
    if y2 > 1:
        bar_roi = display[0:y2, 0:w]
        overlay = bar_roi.copy()
        cv2.rectangle(overlay, (0, 0), (w, y2), (20, 20, 20), -1)
        cv2.addWeighted(overlay, 0.7, bar_roi, 0.3, 0, bar_roi)

    bar_x0 = PADDING + 300
    bar_x1 = w - 200
    bar_y0 = 14
    bar_h = 16
    cv2.rectangle(display, (bar_x0, bar_y0), (bar_x1, bar_y0 + bar_h),
                  COL_PANEL_BG, -1)
    progresso = ex_idx / ex_tot
    fill_w = int((bar_x1 - bar_x0) * progresso)
    if fill_w > 0:
        cv2.rectangle(display, (bar_x0, bar_y0),
                      (bar_x0 + fill_w, bar_y0 + bar_h), COL_VERDE, -1)
    cv2.rectangle(display, (bar_x0, bar_y0), (bar_x1, bar_y0 + bar_h),
                  COL_PANEL_BORDER, 1)

    nome = _truncate(sessione_info.get("program_name", ""), 35)
    cv2.putText(display, nome, (PADDING, 30), FONT, 0.65, COL_BIANCO, 1)

    counter = f"{ex_idx}/{ex_tot}"
    cv2.putText(display, counter, (w - 180, 30), FONT, 0.7, COL_GIALLO, 2)


def _render_lista_esercizi(display, sessione_info, x, y, w, h):
    _panel(display, x, y, w, h)
    cv2.putText(display, "ESERCIZI", (x + 12, y + 26),
                FONT, 0.7, COL_GIALLO, 2)

    esercizi = sessione_info.get("esercizi", [])
    if not esercizi:
        return

    ex_idx = sessione_info.get("exercise_index", 0)
    max_visibili = max(4, (h - 60) // 54)
    start, end = _finestra_scroll(esercizi, ex_idx, max_visibili)

    yy = y + 58
    for i in range(start, end):
        ex = esercizi[i]
        stato = ex.get("stato", "futuro")
        colore = _colore_stato(stato)
        icona = _icona_stato(stato)

        if stato == "corrente":
            cv2.rectangle(display, (x + 6, yy - 22),
                          (x + w - 6, yy + 20), (55, 65, 45), -1)

        nome = _truncate(ex.get("name", ""), 30)
        n_fasi = ex.get("phase_total", 0)
        testo = f"[{icona}] {i + 1}. {nome}"
        cv2.putText(display, testo, (x + 12, yy),
                    FONT, 0.6, colore, 2 if stato == "corrente" else 1)
        if n_fasi > 0:
            cv2.putText(display, f"      {n_fasi} fasi",
                        (x + 12, yy + 18), FONT, 0.48, COL_GRIGIO_SCURO, 1)
        yy += 54

    if start > 0:
        cv2.putText(display, "▲", (x + w - 30, y + 26), FONT, 0.6, COL_GRIGIO, 1)
    if end < len(esercizi):
        cv2.putText(display, "▼", (x + w - 30, y + h - 12), FONT, 0.6, COL_GRIGIO, 1)


def _barra_progresso_colored(display, x, y, w, progresso, warning=False):
    progresso = max(0.0, min(1.0, progresso))
    h = 14
    cv2.rectangle(display, (x, y), (x + w, y + h), COL_PANEL_BG, -1)
    fill_w = int(w * progresso)
    if fill_w > 0:
        colore = COL_ARANCIONE if warning else COL_VERDE
        cv2.rectangle(display, (x, y), (x + fill_w, y + h), colore, -1)
    cv2.rectangle(display, (x, y), (x + w, y + h), COL_PANEL_BORDER, 1)


def _render_countdown_overlay(display, cd, h, w):
    if not cd:
        return
    numero = cd.get("numero", 0)
    testo = str(numero) if numero > 0 else "VIA!"
    colore = COL_VERDE if numero == 0 else COL_GIALLO

    box_w, box_h = 400, 260
    cx, cy = w // 2, h // 2 - 30
    overlay = display.copy()
    cv2.rectangle(overlay,
                  (cx - box_w // 2, cy - box_h // 2),
                  (cx + box_w // 2, cy + box_h // 2),
                  (10, 10, 10), -1)
    cv2.addWeighted(overlay, 0.75, display, 0.25, 0, display)
    cv2.rectangle(display,
                  (cx - box_w // 2, cy - box_h // 2),
                  (cx + box_w // 2, cy + box_h // 2),
                  colore, 3)

    label = "PREPARATI"
    size_lbl = cv2.getTextSize(label, FONT, 1.0, 2)[0]
    cv2.putText(display, label,
                (cx - size_lbl[0] // 2, cy - box_h // 2 + 50),
                FONT, 1.0, colore, 2)

    size_num = cv2.getTextSize(testo, FONT, 4.0, 8)[0]
    cv2.putText(display, testo,
                (cx - size_num[0] // 2, cy + size_num[1] // 2 + 20),
                FONT, 4.0, colore, 8)


def _render_istruzioni_calibrazione(display, es, es_result, x, y, w, h):
    exercise_instructions = es.get("exercise_instructions", "")
    stato_es = es.get("stato", "")

    if stato_es == "ISTRUZIONI":
        cv2.putText(display, "ISTRUZIONI ESERCIZIO",
                    (x + 16, y + 24), FONT, 0.7, COL_GIALLO, 2)
        yy = y + 56
        if exercise_instructions:
            for line in _wrap_text(exercise_instructions, 75):
                if yy > y + h - 80:
                    cv2.putText(display, "...", (x + 16, yy), FONT, 0.5, COL_GRIGIO_SCURO, 1)
                    break
                cv2.putText(display, line, (x + 16, yy), FONT, 0.55, COL_BIANCO, 1)
                yy += 22
        yy += 20
        if yy > y + h - 60:
            yy = y + h - 60
        cv2.putText(display, "Premi SPAZIO per iniziare",
                    (x + 16, yy), FONT, 0.7, COL_VERDE, 2)
        yy += 28
        cv2.putText(display, "(3 secondi di countdown, poi calibrazione)",
                    (x + 16, yy), FONT, 0.5, COL_GRIGIO, 1)
        return

    if stato_es == "COUNTDOWN":
        cv2.putText(display, "PREPARATI...",
                    (x + 16, y + 24), FONT, 0.7, COL_GIALLO, 2)
        yy = y + 56
        cv2.putText(display, "Il countdown sta per finire, preparati al movimento",
                    (x + 16, yy), FONT, 0.55, COL_BIANCO, 1)
        yy += 28
        if exercise_instructions:
            cv2.putText(display, "Movimento che eseguirai:",
                        (x + 16, yy), FONT, 0.55, COL_GIALLO, 1)
            yy += 22
            for line in _wrap_text(exercise_instructions, 75):
                if yy > y + h - 60:
                    cv2.putText(display, "...", (x + 16, yy), FONT, 0.5, COL_GRIGIO_SCURO, 1)
                    break
                cv2.putText(display, line, (x + 16, yy), FONT, 0.5, COL_GRIGIO, 1)
                yy += 20
        return

    cal = es.get("calibration") or {}
    state = cal.get("state", "inizio")
    msg = cal.get("msg", "Calibrazione in corso")
    detail = cal.get("detail", "")
    samples = cal.get("samples", 0)
    samples_target = cal.get("samples_target", 15)
    rng = cal.get("range", 0.0)
    rng_target = cal.get("range_target", 20.0)

    if state == "pronto":
        colore = COL_VERDE
    elif state in ("errore", "range_piccolo"):
        colore = COL_ARANCIONE
    else:
        colore = COL_GIALLO

    cv2.putText(display, "CALIBRAZIONE", (x + 16, y + 24), FONT, 0.7, colore, 2)
    yy = y + 56

    cv2.putText(display, _truncate(msg, 55), (x + 16, yy), FONT, 0.7, colore, 2)
    yy += 32

    if detail:
        for line in _wrap_text(detail, 75):
            if yy > y + h - 200:
                break
            cv2.putText(display, line, (x + 16, yy), FONT, 0.55, COL_BIANCO, 1)
            yy += 22
        yy += 12

    if exercise_instructions and state in ("inizio", "raccolta"):
        cv2.putText(display, "Movimento da eseguire:",
                    (x + 16, yy), FONT, 0.55, COL_GIALLO, 1)
        yy += 22
        for line in _wrap_text(exercise_instructions, 75):
            if yy > y + h - 150:
                cv2.putText(display, "...", (x + 16, yy), FONT, 0.5, COL_GRIGIO_SCURO, 1)
                break
            cv2.putText(display, line, (x + 16, yy), FONT, 0.5, COL_GRIGIO, 1)
            yy += 20
        yy += 8

    if yy > y + h - 100:
        yy = y + h - 100
    cv2.putText(display, f"Campioni: {samples}/{samples_target}",
                (x + 16, yy), FONT, 0.55, COL_BIANCO, 1)
    yy += 22

    range_pct = min(1.0, rng / max(1.0, rng_target))
    _barra_progresso_colored(display, x + 16, yy, w - 100, range_pct, warning=(rng < rng_target))
    yy += 22
    cv2.putText(display, f"Range attuale: {rng:.0f}° (servono {rng_target:.0f}°)",
                (x + 16, yy), FONT, 0.5, COL_GRIGIO, 1)
    yy += 26

    if state == "pronto":
        cv2.putText(display, "✓ Premi SPAZIO per iniziare l'esercizio",
                    (x + 16, yy), FONT, 0.6, COL_VERDE, 2)
    elif state == "errore":
        cv2.putText(display, "Premi SPAZIO per riprovare",
                    (x + 16, yy), FONT, 0.55, COL_ARANCIONE, 1)
    else:
        cv2.putText(display, "Continua il movimento...",
                    (x + 16, yy), FONT, 0.55, COL_GRIGIO, 1)
    yy += 22
    cv2.putText(display, "[C] ricomincia calibrazione",
                (x + 16, yy), FONT, 0.48, COL_GRIGIO_SCURO, 1)


def _render_pannello_esercizio(display, sessione_info, x, y, w, h):
    _panel(display, x, y, w, h)

    es = sessione_info.get("esercizio_corrente")
    if not es:
        cv2.putText(display, "Nessun esercizio attivo", (x + 20, y + 40),
                    FONT, 0.7, COL_GRIGIO, 1)
        return

    es_result = sessione_info.get("esercizio_result", {})
    ex_idx = es.get("exercise_index", 0)
    ex_tot = max(1, es.get("exercise_total", 1))
    stato_es = es.get("stato", "")

    cv2.putText(display, f"Esercizio {ex_idx + 1}/{ex_tot}: {_truncate(es.get('exercise_name', ''), 40)}",
                (x + 16, y + 30), FONT, 0.75, COL_BIANCO, 2)

    if stato_es in ("ISTRUZIONI", "CALIBRAZIONE", "COUNTDOWN"):
        _render_istruzioni_calibrazione(display, es, es_result, x, y + 56, w, h - 56)
        return

    ph_idx = es.get("phase_index", 0)
    ph_tot = max(1, es.get("phase_total", 1))
    reps_done = es.get("reps_completate", 0)
    reps_target = es.get("target_repetitions", 1)

    if reps_target > 1:
        label = f"Ripetizione {reps_done + 1}/{reps_target} · Fase {ph_idx + 1}/{ph_tot}"
    else:
        label = f"Fase {ph_idx + 1}/{ph_tot}"
    cv2.putText(display, label, (x + 16, y + 56), FONT, 0.6, COL_GIALLO, 1)
    
    yy = y + 90

    cv2.putText(display, "FASI:", (x + 16, yy), FONT, 0.6, COL_GIALLO, 1)
    yy += 26

    fasi = es.get("fasi", [])
    max_fasi_vis = max(3, (h - 300) // 34)
    start_f, end_f = _finestra_scroll(fasi, ph_idx, max_fasi_vis)

    for i in range(start_f, end_f):
        f = fasi[i]
        stato = f.get("stato", "futura")
        colore = _colore_stato({"completata": "completato",
                                "corrente": "corrente",
                                "futura": "futuro"}.get(stato, "futuro"))
        icona = _icona_stato({"completata": "completato",
                              "corrente": "corrente",
                              "futura": "futuro"}.get(stato, "futuro"))
        desc = _truncate(f.get("description", ""), 55)
        tipo = f.get("type", "")

        if stato == "corrente":
            cv2.rectangle(display, (x + 12, yy - 20),
                          (x + w - 12, yy + 20), (55, 65, 45), -1)

        testo = f"[{icona}] {i + 1}. {desc}"
        cv2.putText(display, testo, (x + 20, yy), FONT, 0.55, colore, 1)
        cv2.putText(display, f"({tipo})", (x + w - 110, yy),
                    FONT, 0.48, COL_GRIGIO_SCURO, 1)
        yy += 34

    yy += 10
    if not es_result:
        es_result = {}
    pr = es_result.get("phase_result")
    if pr and stato_es == "ESECUZIONE":
        prog = pr.get("progresso", 0.0)
        _barra_progresso_colored(display, x + 16, yy, w - 32, prog)
        yy += 28

    if ph_idx < len(fasi):
        desc_corrente = fasi[ph_idx].get("description", "")
        if desc_corrente:
            cv2.rectangle(display, (x + 12, yy - 22),
                          (x + w - 12, yy + 8), (50, 70, 90), -1)
            cv2.putText(display, _truncate(desc_corrente, 70),
                        (x + 18, yy), FONT, 0.7, COL_BIANCO, 2)
            yy += 34

    if pr:
        msg = _truncate(pr.get("messaggio_ui", ""), 70)
        cv2.putText(display, msg, (x + 16, yy), FONT, 0.6, COL_BIANCO, 1)
        yy += 28

    errori = pr.get("errori", []) if pr else []
    if errori:
        cv2.putText(display, "! CORREZIONI:", (x + 16, yy),
                    FONT, 0.65, COL_ROSSO, 2)
        yy += 26
        for e in errori[:3]:
            cv2.putText(display, f"  • {_truncate(e.get('message', e.get('id', '')), 60)}",
                        (x + 16, yy), FONT, 0.58, COL_ROSSO, 1)
            yy += 22
    elif stato_es == "ESECUZIONE":
        cv2.putText(display, "OK Postura corretta", (x + 16, yy),
                    FONT, 0.62, COL_VERDE, 1)
        yy += 26

    yy += 8
    soglie = es.get("soglie_calibrate", {})
    if soglie:
        parti = []
        for tid, s in list(soglie.items())[:3]:
            parti.append(f"{tid}: {s['min']:.0f}-{s['max']:.0f}°")
        txt = " | ".join(parti)
        cv2.putText(display, _truncate("Target cal.: " + txt, 70),
                    (x + 16, yy), FONT, 0.48, COL_GRIGIO_SCURO, 1)


def _render_footer(display, sessione_info, postura, errore_postura, h, w):
    # Ottimizzato: lavora solo sulla fascia bassa (FOOTER_H)
    y1 = max(0, h - FOOTER_H)
    footer_roi = display[y1:h, 0:w]
    overlay = footer_roi.copy()
    cv2.rectangle(overlay, (0, 0), (w, h - y1), (20, 20, 20), -1)
    cv2.addWeighted(overlay, 0.75, footer_roi, 0.25, 0, footer_roi)

    y_top = h - FOOTER_H + 22
    if postura:
        colore_pos = COL_ARANCIONE if errore_postura else COL_GRIGIO
        cv2.putText(display, f"Postura: {postura}", (PADDING, y_top),
                    FONT, 0.6, colore_pos, 1)

    es = sessione_info.get("esercizio_corrente")
    stato_es = es.get("stato", "") if es else ""
    if stato_es in ("ISTRUZIONI", "CALIBRAZIONE", "COUNTDOWN"):
        hint = "[SPAZIO] conferma  [C] ricalibra  [ESC] esci"
    else:
        hint = "[N] salta fase  [C] ricalibra  [ESC] esci"
    cv2.putText(display, hint, (w - 400, y_top),
                FONT, 0.5, COL_GRIGIO_SCURO, 1)

    feedback = sessione_info.get("ultimo_feedback", "")
    if feedback:
        fb_time = sessione_info.get("ultimo_feedback_time", 0)
        colore_fb = COL_GIALLO
        if fb_time:
            eta = time.time() - fb_time
            if eta > 10.0:
                colore_fb = COL_GRIGIO_SCURO
        prefisso = "AI: "
        max_chars = int((w - 40) / 9)
        lines = _wrap_text(prefisso + feedback, max_chars)[:2]
        yy = y_top + 26
        for line in lines:
            cv2.putText(display, line, (PADDING, yy),
                        FONT, 0.58, colore_fb, 1)
            yy += 24