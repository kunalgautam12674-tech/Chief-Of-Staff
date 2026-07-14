import json
import os
from datetime import datetime


def log_action(action_type, thread_subject, detail, action_id):
    """Appends a record to action_log.json.

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

    log = get_action_log()
    log.append(record)

    with open("action_log.json", "w") as f:
        json.dump(log, f, indent=2)


def get_action_log():
    """Reads action_log.json and returns the full list.

    Returns [] if the file does not exist or is empty.
    """
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
    """Writes an empty list to action_log.json."""
    with open("action_log.json", "w") as f:
        json.dump([], f)
