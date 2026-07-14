"""
calendar.py - Google Calendar availability checking.

Provides check_calendar_availability() which returns free/busy info
for the next N days, using the same OAuth credentials as engine.py.
"""

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
except ImportError:
    raise ImportError(
        "Missing required packages. Install with:\n"
        "  pip install google-auth-oauthlib google-api-python-client"
    )

# ── Config ────────────────────────────────────────────────────────────────────

SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]

_CONFIG_DIR = Path(os.path.expanduser("~")) / ".gmail-mcp"
_OAUTH_KEYS_PATH = _CONFIG_DIR / "gcp-oauth.keys.json"
_CREDENTIALS_PATH = _CONFIG_DIR / "calendar_credentials.json"


def _get_authenticated_service():
    """Load or refresh credentials and return a Calendar API service object.

    Reuses the same OAuth keys and token file as engine.py, but requests
    the ``calendar.readonly`` scope.
    """
    if not _OAUTH_KEYS_PATH.exists():
        raise FileNotFoundError(
            f"OAuth keys not found. Place gcp-oauth.keys.json "
            f"in {_CONFIG_DIR}"
        )

    with open(str(_OAUTH_KEYS_PATH)) as f:
        keys_data = json.load(f)
    installed = keys_data.get("installed") or keys_data.get("web") or {}
    client_config = {
        "client_id": installed["client_id"],
        "client_secret": installed["client_secret"],
        "redirect_uris": installed.get("redirect_uris", ["http://localhost"]),
    }

    creds = None

    if _CREDENTIALS_PATH.exists():
        with open(str(_CREDENTIALS_PATH)) as f:
            token_data = json.load(f)
        creds = Credentials(
            token=token_data.get("access_token"),
            refresh_token=token_data.get("refresh_token"),
            token_uri="https://oauth2.googleapis.com/token",
            client_id=client_config["client_id"],
            client_secret=client_config["client_secret"],
            scopes=SCOPES,
            expiry=_parse_expiry(token_data.get("expiry_date")),
        )

    if creds is None or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            print("Refreshing expired Calendar token...")
            try:
                creds.refresh(Request())
            except Exception as refresh_err:
                # Token may have been issued for different scopes (e.g. Gmail only).
                # Delete the stale token and re-auth from scratch.
                print(
                    f"  Token refresh failed ({refresh_err}). Re-authenticating...")
                if _CREDENTIALS_PATH.exists():
                    _CREDENTIALS_PATH.unlink()
                creds = None
        if creds is None:
            flow = InstalledAppFlow.from_client_config(
                {"installed": installed}, SCOPES
            )
            creds = flow.run_local_server(port=3001)

        _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        token_data = {
            "access_token": creds.token,
            "refresh_token": creds.refresh_token,
            "scope": " ".join(SCOPES),
            "token_type": "Bearer",
            "expiry_date": (
                int(creds.expiry.timestamp() * 1000) if creds.expiry else 0
            ),
        }
        with open(str(_CREDENTIALS_PATH), "w") as f:
            json.dump(token_data, f)

    return build("calendar", "v3", credentials=creds)


def _parse_expiry(expiry_date):
    """Convert a millisecond timestamp to a naive UTC datetime, or return None."""
    if expiry_date:
        import datetime as dt
        try:
            return dt.datetime.fromtimestamp(expiry_date / 1000, tz=timezone.utc).replace(tzinfo=None)
        except Exception:
            pass
    return None


def _format_busy_slots(busy_periods: list[dict]) -> str:
    """Format busy periods into a human-readable summary string."""
    if not busy_periods:
        return "  No events found — calendar appears clear."

    # Group by date
    from collections import defaultdict
    by_date = defaultdict(list)
    for period in busy_periods:
        start = datetime.fromisoformat(period["start"].replace("Z", "+00:00"))
        end = datetime.fromisoformat(period["end"].replace("Z", "+00:00"))
        date_key = start.strftime("%A, %B %d")
        time_range = f"{start.strftime('%I:%M %p').lstrip('0')} – {end.strftime('%I:%M %p').lstrip('0')}"
        by_date[date_key].append(time_range)

    lines = []
    for date_key in sorted(by_date.keys()):
        lines.append(f"  {date_key}:")
        for tr in by_date[date_key]:
            lines.append(f"    - Busy: {tr}")
    return "\n".join(lines)


def check_calendar_availability(days_ahead: int = 7) -> str:
    """Fetch free/busy info for the primary calendar for the next *days_ahead* days.

    Parameters
    ----------
    days_ahead : int
        How many days from today to check (default 7).

    Returns
    -------
    str
        A human-readable summary of busy periods, suitable for injecting
        into an AI prompt.
    """
    service = _get_authenticated_service()

    now = datetime.now(timezone.utc)
    time_min = now.isoformat()
    time_max = (now + timedelta(days=days_ahead)).isoformat()

    body = {
        "timeMin": time_min,
        "timeMax": time_max,
        "items": [{"id": "primary"}],
    }

    try:
        result = service.freebusy().query(body=body).execute()
        calendars = result.get("calendars", {})
        primary = calendars.get("primary", {})
        busy = primary.get("busy", [])

        summary = _format_busy_slots(busy)
        return (
            f"Your calendar availability for the next {days_ahead} days:\n"
            f"{summary}"
        )
    except Exception as e:
        return f"Could not fetch calendar availability: {e}"


if __name__ == "__main__":
    print(check_calendar_availability(3))
