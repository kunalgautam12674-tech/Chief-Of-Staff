import json
import os
from datetime import datetime


def log_action(action_type, thread_subject, detail, action_id):
    """Appends a record to action log using Streamlit session state or file fallback.

    Args:
        action_type: "sent" or "booked"
        thread_subject: The subject line of the email thread
        detail: Recipient email (for "sent") or meeting title (for "booked")
        action_id: Gmail message_id or Google Calendar event_id
    """
    record = {
        "timestamp": datetime.now().isoformat(),
        "action_type": action_type,
        "thread_subject": thread_subject,
        "detail": detail,
        "id": action_id,
    }

    # Try to use Streamlit session state first (for cloud deployment)
    try:
        import streamlit as st
        if hasattr(st, 'session_state'):
            if 'action_log' not in st.session_state:
                st.session_state.action_log = []
            st.session_state.action_log.append(record)
            return
    except ImportError:
        pass

    # Fall back to file-based persistence (for local development)
    log = get_action_log()
    log.append(record)

    with open("action_log.json", "w") as f:
        json.dump(log, f, indent=2)


def get_action_log():
    """Reads action log from Streamlit session state or file fallback.

    Returns [] if no log exists.
    """
    # Try Streamlit session state first (for cloud deployment)
    try:
        import streamlit as st
        if hasattr(st, 'session_state') and 'action_log' in st.session_state:
            return st.session_state.action_log
    except ImportError:
        pass

    # Fall back to file-based persistence (for local development)
    if not os.path.exists("action_log.json"):
        return []

    try:
        with open("action_log.json", "r") as f:
            content = f.read().strip()
            if not content:
                return []
            return json.loads(content)
    except (json.JSONDecodeError, IOError):
        return []


def clear_log():
    """Clears the action log from Streamlit session state or file fallback."""
    # Try Streamlit session state first (for cloud deployment)
    try:
        import streamlit as st
        if hasattr(st, 'session_state'):
            st.session_state.action_log = []
            return
    except ImportError:
        pass

    # Fall back to file-based persistence (for local development)
    with open("action_log.json", "w") as f:
        json.dump([], f)
