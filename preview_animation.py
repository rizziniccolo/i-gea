import math
import time
import cv2

FONT = cv2.FONT_HERSHEY_SIMPLEX

COL_BASE = (140, 140, 140)
COL_GHOST = (80, 80, 80)
COL_ACTIVE = (0, 220, 255)
COL_CURRENT = (0, 120, 255)
COL_BG = (25, 25, 25)
COL_BORDER = (90, 90, 90)
COL_TEXT = (240, 240, 240)

ANIM_SPEED = 1.5

SEGMENT_MAP = {
    "shoulder_right": {"pivot": "shoulder_r", "length": 30, "sign": 1, "base": 0,
                       "skip": {"upper_arm_right", "forearm_right"}},
    "shoulder_left":  {"pivot": "shoulder_l", "length": 30, "sign": -1, "base": 0,
                       "skip": {"upper_arm_left", "forearm_left"}},
    "elbow_right":    {"pivot": "elbow_r", "length": 22, "sign": 1, "base": 180,
                       "skip": {"forearm_right"}},
    "elbow_left":     {"pivot": "elbow_l", "length": 22, "sign": -1, "base": 180,
                       "skip": {"forearm_left"}},
    "hip_right":      {"pivot": "hip_r", "length": 25, "sign": 1, "base": 180,
                       "skip": {"thigh_right", "shin_right"}},
    "hip_left":       {"pivot": "hip_l", "length": 25, "sign": -1, "base": 180,
                       "skip": {"thigh_left", "shin_left"}},
    "knee_right":     {"pivot": "knee_r", "length": 25, "sign": 1, "base": 180,
                       "skip": {"shin_right"}},
    "knee_left":      {"pivot": "knee_l", "length": 25, "sign": -1, "base": 180,
                       "skip": {"shin_left"}},
}


def _truncate(text, max_chars):
    if not text:
        return ""
    return text if len(text) <= max_chars else text[:max_chars - 1] + "…"


def _draw_base_body(display, cx, cy, scale, skip=None):
    skip = skip or set()
    cx_i = int(cx)
    cy_i = int(cy)
    head_r = max(1, int(8 * scale))
    neck_y = int(cy_i - 30 * scale)
    shoulder_y = int(cy_i - 25 * scale)
    hip_y = int(cy_i + 15 * scale)
    knee_y = int(cy_i + 40 * scale)
    ankle_y = int(cy_i + 65 * scale)
    shoulder_off = int(12 * scale)
    hip_off = int(8 * scale)

    points = {}

    head_cy = int(neck_y - head_r - 2 * scale)
    cv2.circle(display, (cx_i, head_cy), head_r, COL_BASE, 2)
    points["head"] = (cx_i, head_cy)

    points["neck"] = (cx_i, neck_y)
    cv2.line(display, (cx_i, int(neck_y - 2 * scale)),
             (cx_i, int(neck_y + 2 * scale)), COL_BASE, 1)

    cv2.line(display, (cx_i, neck_y), (cx_i, hip_y), COL_BASE, 2)

    points["shoulder_l"] = (cx_i - shoulder_off, shoulder_y)
    points["shoulder_r"] = (cx_i + shoulder_off, shoulder_y)
    cv2.line(display, points["shoulder_l"], points["shoulder_r"], COL_BASE, 2)

    elbow_r = (cx_i + shoulder_off + int(4 * scale), int(shoulder_y + 22 * scale))
    wrist_r = (cx_i + shoulder_off + int(6 * scale), int(shoulder_y + 42 * scale))
    elbow_l = (cx_i - shoulder_off - int(4 * scale), int(shoulder_y + 22 * scale))
    wrist_l = (cx_i - shoulder_off - int(6 * scale), int(shoulder_y + 42 * scale))
    points["elbow_r"] = elbow_r
    points["wrist_r"] = wrist_r
    points["elbow_l"] = elbow_l
    points["wrist_l"] = wrist_l

    if "upper_arm_right" not in skip:
        cv2.line(display, points["shoulder_r"], elbow_r, COL_BASE, 2)
    if "forearm_right" not in skip:
        cv2.line(display, elbow_r, wrist_r, COL_BASE, 2)
    if "upper_arm_left" not in skip:
        cv2.line(display, points["shoulder_l"], elbow_l, COL_BASE, 2)
    if "forearm_left" not in skip:
        cv2.line(display, elbow_l, wrist_l, COL_BASE, 2)

    points["hip_l"] = (cx_i - hip_off, hip_y)
    points["hip_r"] = (cx_i + hip_off, hip_y)
    cv2.line(display, points["hip_l"], points["hip_r"], COL_BASE, 2)

    knee_r = (cx_i + hip_off, knee_y)
    ankle_r = (cx_i + hip_off + int(2 * scale), ankle_y)
    knee_l = (cx_i - hip_off, knee_y)
    ankle_l = (cx_i - hip_off - int(2 * scale), ankle_y)
    points["knee_r"] = knee_r
    points["ankle_r"] = ankle_r
    points["knee_l"] = knee_l
    points["ankle_l"] = ankle_l

    if "thigh_right" not in skip:
        cv2.line(display, points["hip_r"], knee_r, COL_BASE, 2)
    if "shin_right" not in skip:
        cv2.line(display, knee_r, ankle_r, COL_BASE, 2)
    if "thigh_left" not in skip:
        cv2.line(display, points["hip_l"], knee_l, COL_BASE, 2)
    if "shin_left" not in skip:
        cv2.line(display, knee_l, ankle_l, COL_BASE, 2)

    return points


def _compute_segment_endpoint(pivot, angle, base, sign, length):
    if base == 0:
        seg_angle = angle * sign
    else:
        seg_angle = (180 - angle) * sign
    a = math.radians(seg_angle)
    px, py = pivot
    ex = px + length * math.sin(a)
    ey = py + length * math.cos(a)
    return ex, ey


def _draw_active_segment(display, pivot, angle, base, sign, length, color, thickness=3):
    if angle is None:
        return
    ex, ey = _compute_segment_endpoint(pivot, angle, base, sign, length)
    cv2.line(display, (int(pivot[0]), int(pivot[1])), (int(ex), int(ey)), color, thickness)
    cv2.circle(display, (int(ex), int(ey)), max(2, thickness), color, -1)


def _draw_ghost_segment(display, pivot, angle, base, sign, length):
    if angle is None:
        return
    ex, ey = _compute_segment_endpoint(pivot, angle, base, sign, length)
    px, py = int(pivot[0]), int(pivot[1])
    ex, ey = int(ex), int(ey)
    dx = ex - px
    dy = ey - py
    steps = max(2, int(math.sqrt(dx*dx + dy*dy) / 5))
    for i in range(0, steps, 2):
        t0 = i / steps
        t1 = min(1.0, (i + 1) / steps)
        x0 = int(px + dx * t0)
        y0 = int(py + dy * t0)
        x1 = int(px + dx * t1)
        y1 = int(py + dy * t1)
        cv2.line(display, (x0, y0), (x1, y1), COL_GHOST, 1)


def _draw_generic_fallback(display, cx, cy, scale, angle, vertex):
    r = int(28 * scale)
    cv2.circle(display, (int(cx), int(cy)), r, COL_BASE, 2)
    cv2.circle(display, (int(cx), int(cy)), 3, COL_BASE, -1)

    if angle is not None:
        a = math.radians(angle)
        ex = cx + r * math.sin(a)
        ey = cy + r * math.cos(a)
        cv2.arrowedLine(display, (int(cx), int(cy)), (int(ex), int(ey)),
                        COL_ACTIVE, 2, tipLength=0.3)
        cv2.circle(display, (int(ex), int(ey)), max(2, int(4 * scale)), COL_ACTIVE, -1)

    label = _truncate(vertex, 14)
    cv2.putText(display, label,
                (int(cx - r), int(cy + r + 14)),
                FONT, 0.4, COL_BASE, 1)


def _compute_expected_angle(preview_data, t):
    ph_type = preview_data.get("phase_type", "")
    min_v = preview_data.get("min")
    max_v = preview_data.get("max")
    to_range = preview_data.get("to_range")
    from_range = preview_data.get("from_range")

    if ph_type == "hold":
        if min_v is not None and max_v is not None:
            return (min_v + max_v) / 2.0
        if min_v is not None:
            return min_v
        if max_v is not None:
            return max_v
        return 90.0

    if ph_type == "movement" and to_range and len(to_range) >= 2:
        to_lo = to_range[0] if to_range[0] is not None else 0
        to_hi = to_range[1] if to_range[1] is not None else 180
        to_center = (to_lo + to_hi) / 2.0
        if from_range and len(from_range) >= 2:
            fr_lo = from_range[0] if from_range[0] is not None else to_lo
            fr_hi = from_range[1] if from_range[1] is not None else to_hi
            fr_center = (fr_lo + fr_hi) / 2.0
        else:
            fr_center = to_lo if to_lo is not None else 0
        lo, hi = min(fr_center, to_center), max(fr_center, to_center)
        phase = 0.5 + 0.5 * math.sin(t * ANIM_SPEED)
        return lo + (hi - lo) * phase

    if min_v is not None and max_v is not None:
        lo, hi = min_v, max_v
    elif to_range and len(to_range) >= 2:
        lo = to_range[0] if to_range[0] is not None else 0
        hi = to_range[1] if to_range[1] is not None else 180
    else:
        lo, hi = 0, 180

    phase = 0.5 + 0.5 * math.sin(t * ANIM_SPEED)
    return lo + (hi - lo) * phase


def render_preview(display, sessione_info, x, y, size=200):
    """
    Anteprima animata. Lavora SOLO su ROI 200x200 per non rallentare il loop
    principale. Nessun display.copy() o addWeighted sull'intera immagine.
    """
    es = sessione_info.get("esercizio_corrente")
    if not es:
        return
    preview_data = es.get("preview_data")
    if not preview_data:
        return

    h_img, w_img = display.shape[:2]
    x1 = max(0, min(int(x), w_img - 1))
    y1 = max(0, min(int(y), h_img - 1))
    x2 = max(x1 + 1, min(x1 + size, w_img))
    y2 = max(y1 + 1, min(y1 + size, h_img))
    if x2 - x1 < 50 or y2 - y1 < 50:
        return

    # Lavora solo sulla ROI: overlay + blend locali
    roi = display[y1:y2, x1:x2]
    overlay = roi.copy()
    cv2.rectangle(overlay, (0, 0), (x2 - x1, y2 - y1), COL_BG, -1)
    cv2.addWeighted(overlay, 0.65, roi, 0.35, 0, roi)
    cv2.rectangle(display, (x1, y1), (x2, y2), COL_BORDER, 1)

    # Riferimento locale: lavoriamo su `roi` come se fosse un canvas 200x200
    cv2.putText(roi, "ANTEPRIMA", (8, 18), FONT, 0.5, COL_TEXT, 1)

    t = time.time()
    angolo_atteso = _compute_expected_angle(preview_data, t)
    angolo_corrente = None
    mc = sessione_info.get("metriche_correnti")
    if mc:
        angolo_corrente = mc.get(preview_data.get("joint_id"))

    cx = size / 2
    cy = size / 2 + 10
    scale = size / 180.0

    vertex = preview_data.get("vertex", "")
    joint_id = preview_data.get("joint_id", "")

    if vertex in SEGMENT_MAP:
        info = SEGMENT_MAP[vertex]
        points = _draw_base_body(roi, cx, cy, scale, skip=info["skip"])
        pivot = points.get(info["pivot"])
        if pivot:
            length = info["length"] * scale
            base = info["base"]
            sign = info["sign"]

            from_range = preview_data.get("from_range")
            min_v = preview_data.get("min")
            if from_range and len(from_range) >= 2:
                fr_lo = from_range[0] if from_range[0] is not None else min_v
                fr_hi = from_range[1] if from_range[1] is not None else min_v
                if fr_lo is not None and fr_hi is not None:
                    ghost_angle = (fr_lo + fr_hi) / 2.0
                    _draw_ghost_segment(roi, pivot, ghost_angle, base, sign, length)
            elif min_v is not None:
                _draw_ghost_segment(roi, pivot, min_v, base, sign, length)

            _draw_active_segment(roi, pivot, angolo_atteso, base, sign, length,
                                 COL_ACTIVE, thickness=4)
            if angolo_corrente is not None:
                _draw_active_segment(roi, pivot, angolo_corrente, base, sign, length,
                                     COL_CURRENT, thickness=3)
    else:
        _draw_generic_fallback(roi, cx, cy, scale, angolo_atteso, vertex or joint_id)

    if angolo_atteso is not None:
        cv2.putText(roi, f"Target: {angolo_atteso:.0f}°",
                    (8, size - 10), FONT, 0.5, COL_TEXT, 1)

    leg_x = size - 80
    leg_y = 18
    cv2.circle(roi, (leg_x, leg_y - 4), 4, COL_ACTIVE, -1)
    cv2.putText(roi, "atteso", (leg_x + 8, leg_y), FONT, 0.4, COL_BASE, 1)
    cv2.circle(roi, (leg_x, leg_y + 12), 4, COL_CURRENT, -1)
    cv2.putText(roi, "attuale", (leg_x + 8, leg_y + 16), FONT, 0.4, COL_BASE, 1)