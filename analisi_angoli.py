import math


def calcola_angolo(p1, p2, p3):
    """Angolo (gradi) al punto p2, formato da p1-p2-p3. Punti come (x,y,z)."""
    v1 = (p1[0] - p2[0], p1[1] - p2[1], p1[2] - p2[2])
    v2 = (p3[0] - p2[0], p3[1] - p2[1], p3[2] - p2[2])
    dot = v1[0]*v2[0] + v1[1]*v2[1] + v1[2]*v2[2]
    m1 = math.sqrt(v1[0]**2 + v1[1]**2 + v1[2]**2)
    m2 = math.sqrt(v2[0]**2 + v2[1]**2 + v2[2]**2)
    if m1 == 0 or m2 == 0:
        return 0.0
    cos_a = max(-1.0, min(1.0, dot / (m1 * m2)))
    return math.degrees(math.acos(cos_a))


def pos(joint):
    """Estrae (x,y,z) da un Joint di kinect-next."""
    return (joint.position.x, joint.position.y, joint.position.z)


# --- PRIMITIVE GENERICHE ---

def angolo_tra_giunti(joints, nomi):
    """nomi: [estremo1, vertice, estremo2] (3 nomi di giunti)."""
    if len(nomi) != 3:
        return None
    try:
        a, b, c = [pos(getattr(joints, n)) for n in nomi]
        return calcola_angolo(a, b, c)
    except AttributeError:
        return None


def distanza_verticale_giunti(joints, nome_a, nome_b):
    """Differenza |y_a - y_b| in cm."""
    try:
        a = pos(getattr(joints, nome_a))
        b = pos(getattr(joints, nome_b))
        return abs(a[1] - b[1]) * 100
    except AttributeError:
        return None


def inclinazione_verticale(joints, nome_a, nome_b):
    """Angolo tra il vettore a→b e l'asse verticale (0,1,0)."""
    try:
        a = pos(getattr(joints, nome_a))
        b = pos(getattr(joints, nome_b))
    except AttributeError:
        return None
    v = (b[0]-a[0], b[1]-a[1], b[2]-a[2])
    m = math.sqrt(v[0]**2 + v[1]**2 + v[2]**2)
    if m == 0:
        return 0.0
    cos_a = max(-1.0, min(1.0, v[1] / m))
    return math.degrees(math.acos(cos_a))


# --- REGISTRO COMPENSAZIONI ---

def _comp_angle(joints, comp):
    return angolo_tra_giunti(joints, comp.get("joints", []))


def _comp_angle_from_vertical(joints, comp):
    j = comp.get("joints", ["spine_base", "spine_shoulder"])
    if len(j) != 2:
        return None
    return inclinazione_verticale(joints, j[0], j[1])


def _comp_distance_vertical(joints, comp):
    j = comp.get("joints", [])
    if len(j) != 2:
        return None
    return distanza_verticale_giunti(joints, j[0], j[1])


COMPENSAZIONI_DISPONIBILI = {
    "angle":               _comp_angle,
    "angle_from_vertical": _comp_angle_from_vertical,
    "distance_vertical":   _comp_distance_vertical,
}


def valore_compensazione(joints, comp):
    """Unica fonte di verità. Restituisce None se il tipo non è supportato."""
    fn = COMPENSAZIONI_DISPONIBILI.get(comp.get("type"))
    if fn is None:
        return None
    return fn(joints, comp)


# --- TRACCIAMENTO DINAMICO ---

def giunti_richiesti_da_ricetta(ricetta):
    """Estrae l'insieme di giunti necessari per eseguire la ricetta."""
    richiesti = set()
    for target in ricetta.get("target_joints", []):
        for j in target.get("joints", []):
            richiesti.add(j)
    for comp in ricetta.get("compensations_to_monitor", []):
        for j in comp.get("joints", []):
            richiesti.add(j)
        if comp.get("type") == "angle_from_vertical" and not comp.get("joints"):
            richiesti.update(["spine_base", "spine_shoulder"])
    return richiesti


def articolazioni_tracciate(joints, nomi_richiesti):
    """
    True SOLO se tutti i giunti sono TRACKED.
    Rifiuta INFERRED e NOT_TRACKED.
    """
    from kinect_next.models.body import TrackingState
    for nome in nomi_richiesti:
        try:
            j = getattr(joints, nome)
            if j.tracking_state != TrackingState.TRACKED:
                return False
        except AttributeError:
            return False
    return True

# --- GESTO OK PARAMETRICO ---

def rileva_gesto_ok(joints, mano="right", soglia_cm=5.0):
    suffix = f"_{mano}"
    try:
        thumb = pos(getattr(joints, f"thumb{suffix}"))
        tip = pos(getattr(joints, f"hand_tip{suffix}"))
    except AttributeError:
        return False
    d = math.sqrt(
        (thumb[0]-tip[0])**2 +
        (thumb[1]-tip[1])**2 +
        (thumb[2]-tip[2])**2
    ) * 100
    return d < soglia_cm


# --- CLASSIFICAZIONE POSTURA ---

def classifica_postura(joints):
    """
    Classifica la postura del corpo in base a relazioni geometriche tra giunti.
    Restituisce: "in_piedi", "seduto", "sdraiato", "inginocchiato",
    "accovacciato", "sconosciuta".

    Usa tre segnali combinati:
    - angolo medio delle ginocchia
    - inclinazione del tronco rispetto alla verticale
    - differenza verticale testa-bacino

    Il solo angolo delle ginocchia è insufficiente: un utente seduto con le
    gambe distese ha ginocchia estese ma non è in piedi; la differenza
    testa-bacino lo smaschera.
    """
    from kinect_next.models.body import TrackingState

    # Se il bacino non è tracciato, il risultato non è affidabile
    try:
        if joints.spine_base.tracking_state == TrackingState.NOT_TRACKED:
            return "sconosciuta"
    except AttributeError:
        return "sconosciuta"

    try:
        knee_r = angolo_tra_giunti(joints, ["hip_right", "knee_right", "ankle_right"])
        knee_l = angolo_tra_giunti(joints, ["hip_left", "knee_left", "ankle_left"])
        trunk = inclinazione_verticale(joints, "spine_base", "spine_shoulder")
        head_y = pos(joints.head)[1]
        base_y = pos(joints.spine_base)[1]
        delta_testa_bacino_cm = abs(head_y - base_y) * 100
    except AttributeError:
        return "sconosciuta"

    valid_knees = [k for k in (knee_r, knee_l) if k is not None]
    if not valid_knees:
        return "sconosciuta"
    knee = sum(valid_knees) / len(valid_knees)

    # Sdraiato: tronco quasi orizzontale, oppure testa e bacino alla stessa altezza
    if trunk is not None and trunk > 60:
        return "sdraiato"
    if delta_testa_bacino_cm < 20:
        return "sdraiato"

    # In piedi: ginocchia estese, testa ben sopra il bacino
    if knee > 150 and delta_testa_bacino_cm > 60:
        return "in_piedi"

    # Seduto: ginocchia flesse ~90° (o distese se su divano), tronco verticale
    if 40 <= delta_testa_bacino_cm <= 75:
        return "seduto"

    # Inginocchiato: ginocchia molto flesse ma tronco ancora verticale
    if knee < 70 and delta_testa_bacino_cm > 40:
        return "inginocchiato"

    # Accovacciato: ginocchia molto flesse E bacino molto vicino ai piedi
    if knee < 110 and delta_testa_bacino_cm < 50:
        return "accovacciato"

    return "sconosciuta"