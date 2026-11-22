import threading
import time
from collections import deque

import requests

N8N_RECIPE_URL = "http://localhost:5678/webhook/kinect-recipe"
N8N_FEEDBACK_URL = "http://localhost:5678/webhook/kinect-feedback"
N8N_PLAN_URL = "http://localhost:5678/webhook/kinect-plan"
N8N_REPORT_URL = "http://localhost:5678/webhook/kinect-report"

TIMEOUT_PROGRAMMA = 180
TIMEOUT_FEEDBACK = 30
TIMEOUT_PLAN = 60
TIMEOUT_REPORT = 30


class HistoryBuffer:
    def __init__(self, maxlen=5):
        self._buf = deque(maxlen=maxlen)

    def add(self, exercise_id, phase_id, phase_type, metrics, errors, feedback=None):
        self._buf.append({
            "exercise_id": exercise_id,
            "phase_id": phase_id,
            "phase_type": phase_type,
            "metrics": metrics,
            "errors": errors,
            "feedback_given": feedback,
            "timestamp": time.time(),
        })

    def snapshot(self):
        return list(self._buf)

    def clear(self):
        self._buf.clear()


def _post_async(url, packet, callback, error_label, timeout):
    def _worker():
        print(f"\n[THREAD] POST {url} (timeout={timeout}s)")
        try:
            r = requests.post(url, json=packet, timeout=timeout)
            r.raise_for_status()
            try:
                data = r.json()
            except ValueError:
                data = {"error": "Risposta non JSON", "raw": r.text[:200]}
            if callback:
                callback(data)
        except requests.exceptions.Timeout:
            print(f"[THREAD] Timeout {error_label} dopo {timeout}s")
            if callback:
                callback({"error": f"timeout ({error_label})"})
        except requests.exceptions.RequestException as e:
            print(f"[THREAD] Errore {error_label}: {e}")
            if callback:
                callback({"error": str(e)})

    t = threading.Thread(target=_worker, daemon=True)
    t.start()


def invia_richiesta_programma(diagnosi, answers=None, previous_questions=None,
                               revision_note=None, previous_program=None,
                               callback=None):
    packet = {"action": "generate_recipe", "diagnosis": diagnosi}
    if answers is not None:
        packet["answers"] = answers
    if previous_questions is not None:
        packet["previous_questions"] = previous_questions
    if revision_note is not None:
        packet["revision_note"] = revision_note
    if previous_program is not None:
        packet["previous_program"] = previous_program
    _post_async(N8N_RECIPE_URL, packet, callback, "programma", TIMEOUT_PROGRAMMA)


def invia_evento_step(packet, callback=None):
    _post_async(N8N_FEEDBACK_URL, packet, callback, "step", TIMEOUT_FEEDBACK)


def invia_piano(packet, callback=None):
    _post_async(N8N_PLAN_URL, packet, callback, "plan", TIMEOUT_PLAN)


def invia_report(packet, callback=None):
    _post_async(N8N_REPORT_URL, packet, callback, "report", TIMEOUT_REPORT)


def invia_evento_ripetizione(packet, callback=None):
    _post_async(N8N_FEEDBACK_URL, packet, callback, "rep", TIMEOUT_FEEDBACK)