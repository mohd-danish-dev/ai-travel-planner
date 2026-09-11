"""
In-memory conversation history, keyed by session_id.

This is a POC-level choice: state lives in a plain process-wide dict, so
it's lost on restart and won't work if you ever run multiple backend
instances behind a load balancer. Good enough for a local single-user demo;
a real deployment would swap this for Redis or a database without touching
the rest of the orchestrator.
"""

MAX_TURNS_KEPT = 6  # keep the last N (user, assistant) turn pairs per session

_sessions: dict[str, list[dict]] = {}


def get_history(session_id: str) -> list[dict]:
    return _sessions.get(session_id, [])


def add_turn(session_id: str, user_message: str, assistant_message: str):
    history = _sessions.setdefault(session_id, [])
    history.append({"role": "user", "content": user_message})
    history.append({"role": "assistant", "content": assistant_message})
    # trim to the last MAX_TURNS_KEPT turns (2 messages per turn)
    excess = len(history) - MAX_TURNS_KEPT * 2
    if excess > 0:
        del history[:excess]


def clear_session(session_id: str):
    _sessions.pop(session_id, None)
