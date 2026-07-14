"""
calendar_engine.py - Google Calendar API service builder.

Provides _build_calendar_service() which returns an authenticated
Calendar v3 service object, sharing the same OAuth credentials and
scopes as the Gmail engine.
"""

import requests.packages.urllib3.util.connection as urllib3_cn
import json
import os
import socket
from pathlib import Path


def load_env():
    """Load .env file manually without requiring python-dotenv.
    Falls back to Streamlit secrets if available.
    """
    # Try Streamlit secrets first (for cloud deployment)
    try:
        import streamlit as st
        if hasattr(st, 'secrets'):
            try:
                for key in ['GEMINI_API_KEY', 'GOOGLE_CREDENTIALS_JSON', 
                           'OAUTH_ACCESS_TOKEN', 'OAUTH_REFRESH_TOKEN',
                           'OAUTH_CLIENT_ID', 'OAUTH_CLIENT_SECRET']:
                    if key in st.secrets:
                        os.environ.setdefault(key, st.secrets[key])
            except Exception:
                # No secrets file exists, fall back to .env
                pass
    except ImportError:
        pass
    
    # Fall back to .env file (for local development)
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, val = line.partition("=")
                    os.environ.setdefault(key.strip(), val.strip())


load_env()

# ── IPv4 monkey-patch ────────────────────────────────────────────────────────
# Force urllib3 / requests to use IPv4 only, avoiding IPv6 DNS resolution
# delays on misconfigured networks.


def _allowed_gateways():
    return [socket.AF_INET]


urllib3_cn.allowed_gateways = _allowed_gateways

# ── Google API imports ───────────────────────────────────────────────────────

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

# ── Shared scopes (must match engine.py) ─────────────────────────────────────

SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.settings.basic",
    "https://www.googleapis.com/auth/calendar",
]

_CONFIG_DIR = Path(os.path.expanduser("~")) / ".gmail-mcp"
_OAUTH_KEYS_PATH = _CONFIG_DIR / "gcp-oauth.keys.json"
_CREDENTIALS_PATH = _CONFIG_DIR / "credentials.json"


def _build_calendar_service():
    """Load or refresh credentials and return a Calendar v3 API service object.

    Supports both local file-based credentials and Streamlit secrets for cloud deployment.
    """
    # Try Streamlit secrets first (for cloud deployment)
    try:
        import streamlit as st
        if hasattr(st, 'secrets'):
            try:
                # Check for service account credentials (recommended for production)
                if 'GOOGLE_CREDENTIALS_JSON' in st.secrets:
                    from google.oauth2.service_account import Credentials as ServiceAccountCredentials
                    creds_dict = json.loads(st.secrets['GOOGLE_CREDENTIALS_JSON'])
                    creds = ServiceAccountCredentials.from_service_account_info(
                        creds_dict, scopes=SCOPES
                    )
                    return build("calendar", "v3", credentials=creds, cache_discovery=False)
                
                # Check for pre-authorized OAuth tokens (alternative for development)
                if all(k in st.secrets for k in ['OAUTH_ACCESS_TOKEN', 'OAUTH_REFRESH_TOKEN',
                                                  'OAUTH_CLIENT_ID', 'OAUTH_CLIENT_SECRET']):
                    creds = Credentials(
                        token=st.secrets['OAUTH_ACCESS_TOKEN'],
                        refresh_token=st.secrets['OAUTH_REFRESH_TOKEN'],
                        token_uri="https://oauth2.googleapis.com/token",
                        client_id=st.secrets['OAUTH_CLIENT_ID'],
                        client_secret=st.secrets['OAUTH_CLIENT_SECRET'],
                        scopes=SCOPES,
                    )
                    if creds.expired and creds.refresh_token:
                        creds.refresh(Request())
                    return build("calendar", "v3", credentials=creds, cache_discovery=False)
            except Exception:
                # No secrets file exists, fall back to local files
                pass
    except ImportError:
        pass

    # Fall back to local file-based credentials (for local development)
    if not _OAUTH_KEYS_PATH.exists():
        raise FileNotFoundError(
            f"OAuth keys not found. Place gcp-oauth.keys.json "
            f"in {_CONFIG_DIR} or configure Streamlit secrets for cloud deployment."
        )

    # Read the OAuth keys to get client_id / client_secret / redirect_uris
    with open(str(_OAUTH_KEYS_PATH)) as f:
        keys_data = json.load(f)
    installed = keys_data.get("installed") or keys_data.get("web") or {}
    client_config = {
        "client_id": installed["client_id"],
        "client_secret": installed["client_secret"],
        "redirect_uris": installed.get("redirect_uris", ["http://localhost"]),
    }

    creds = None

    # If a saved token exists, reconstruct a Credentials object manually
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

    # If credentials don't exist or are expired, refresh or re-auth
    if creds is None or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            print("Refreshing expired token for Calendar...")
            creds.refresh(Request())
        else:
            # Run the OAuth flow (opens a browser) - only works locally
            flow = InstalledAppFlow.from_client_config(
                {"installed": installed}, SCOPES
            )
            creds = flow.run_local_server(port=3000)

        # Save credentials for next run (include expiry_date as timestamp)
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

    return build("calendar", "v3", credentials=creds, cache_discovery=False)


def _parse_expiry(expiry_date):
    """Convert a millisecond timestamp to a naive UTC datetime, or return None."""
    if expiry_date:
        import datetime
        try:
            return datetime.datetime.fromtimestamp(
                expiry_date / 1000, tz=datetime.timezone.utc
            ).replace(tzinfo=None)
        except Exception:
            pass
    return None


# ── Meeting request parsing ──────────────────────────────────────────────────


def _call_gemini_with_retry(prompt: str, model: str = "gemini-2.5-flash") -> str:
    """Call Gemini API with exponential backoff retry for rate limits."""
    import time
    import random
    from google.genai import errors

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY environment variable not set")

    from google import genai
    client = genai.Client(api_key=api_key)

    _MAX_RETRIES = 3
    _BASE_DELAY = 2.0  # seconds
    _MAX_TOTAL_TIME = 30  # seconds total timeout

    start_time = time.time()

    for attempt in range(_MAX_RETRIES):
        if time.time() - start_time > _MAX_TOTAL_TIME:
            raise RuntimeError(
                f"Timeout after {time.time() - start_time:.1f}s due to persistent rate limiting.")

        try:
            response = client.models.generate_content(
                model=model,
                contents=prompt,
            )
            return response.text.strip()
        except errors.ClientError as e:
            error_str = str(e)
            if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str or "quota" in error_str.lower():
                if attempt < _MAX_RETRIES - 1:
                    base_delay = _BASE_DELAY * (2 ** attempt)
                    jitter = random.uniform(0.5, 1.5)
                    retry_delay = min(base_delay * jitter, 5.0)
                    print(
                        f"  ⏳ Rate limited (attempt {attempt + 1}/{_MAX_RETRIES}). Retrying in {retry_delay:.1f}s...")
                    time.sleep(retry_delay)
                else:
                    raise RuntimeError(
                        f"Failed after {_MAX_RETRIES} retries due to persistent rate limiting.")
            else:
                raise
    raise RuntimeError(f"Failed after {_MAX_RETRIES} retries")


def _parse_gemini_response(raw: str) -> dict | None:
    """Parse Gemini JSON response, stripping markdown fences if present."""
    cleaned = raw
    if cleaned.startswith("```"):
        first_newline = cleaned.find("\n")
        if first_newline != -1:
            cleaned = cleaned[first_newline + 1:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3].strip()
        elif "```" in cleaned:
            cleaned = cleaned.split("```")[0].strip()

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        return None


def _parse_natural_date(text: str, today) -> list:
    """Parse natural language date/time strings into ISO-8601 datetime strings.

    Handles formats like:
      "Tuesday, July 14 at 3:00 PM IST"
      "Thursday at 7:00 PM"
      "July 16 at 7 PM"
      "2026-07-14T15:00:00"
      "tomorrow at 10am"
    """
    import datetime as dt
    import re

    results = []
    month_map = {
        "january": 1, "february": 2, "march": 3, "april": 4,
        "may": 5, "june": 6, "july": 7, "august": 8,
        "september": 9, "october": 10, "november": 11, "december": 12,
        "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6,
        "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
    }

    # Pattern: "Day, Month Day at H:MM AM/PM" or "Month Day at H:MM AM/PM"
    # Uses a wide pattern then validates month from the extracted text
    date_pattern = re.compile(
        r'('
        r'(?:[A-Z][a-z]+day,?\s+)?'           # optional day name + comma
        r'[A-Z][a-z]+\s+\d{1,2}'             # month + day number
        r')'
        r'(?:,?\s*|,\s*)'                     # separator
        r'(?:at\s+)?'                         # optional "at"
        r'(\d{1,2})'                           # hour
        r'(?::(\d{2}))?'                       # optional minute
        r'\s*(AM|PM|am|pm|a\.m\.|p\.m\.)'     # AM/PM
    )

    for match in date_pattern.finditer(text):
        date_part = match.group(1)
        hour = int(match.group(2))
        minute = int(match.group(3)) if match.group(3) else 0
        ampm = match.group(4).lower().replace(".", "")[0]

        # Extract month name from date_part
        month_name = None
        for mname in month_map:
            if mname in date_part.lower():
                month_name = mname
                break
        if not month_name:
            continue

        # Extract day number
        day_match = re.search(r'(\d{1,2})', date_part)
        if not day_match:
            continue
        day_num = int(day_match.group(1))

        month_num = month_map[month_name]
        if ampm == "p" and hour < 12:
            hour += 12
        if ampm == "a" and hour == 12:
            hour = 0

        try:
            year = today.year
            event_date = dt.date(year, month_num, day_num)
            if event_date < today:
                event_date = dt.date(year + 1, month_num, day_num)

            event_dt = dt.datetime.combine(event_date, dt.time(hour, minute))
            # Use IST offset (+05:30) as default timezone
            ist_off = dt.timedelta(hours=5, minutes=30)
            event_dt = event_dt.replace(tzinfo=dt.timezone(ist_off))
            iso = event_dt.isoformat()
            if iso not in results:
                results.append(iso)
        except (ValueError, OverflowError):
            continue

    # Pattern: ISO format
    for match in re.finditer(r'\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(?::\d{2})?', text):
        iso_str = match.group(0).replace(" ", "T")
        if not re.search(r':\d{2}$', iso_str):
            iso_str += ":00"
        if iso_str not in results:
            results.append(iso_str)

    # Pattern: relative like "tomorrow at 10am"
    if re.search(r'\btomorrow\b', text, re.IGNORECASE):
        target = today + dt.timedelta(days=1)
        tm = re.search(r'(\d{1,2})(?::(\d{2}))?\s*(AM|PM|am|pm)', text)
        if tm:
            h, m = int(tm.group(1)), int(tm.group(2) or 0)
            ap = tm.group(3).lower()[0]
            if ap == "p" and h < 12:
                h += 12
            if ap == "a" and h == 12:
                h = 0
            d = dt.datetime.combine(target, dt.time(h, m))
            ist = dt.timezone(dt.timedelta(hours=5, minutes=30))
            results.append(d.replace(tzinfo=ist).isoformat())

    return results


def _parse_meeting_with_regex(thread: dict) -> dict:
    """Fallback regex-based meeting parser when Gemini API is rate-limited.

    Uses improved natural language date parsing.
    """
    import datetime as dt
    import re

    messages = thread.get("messages", [])
    if not messages:
        return {
            "parsing_error": "thread has no messages",
            "raw": "",
        }

    full_text = "\n\n".join([msg.get("body", "") for msg in messages])

    # Extract topic (first line or subject-like content)
    topic = ""
    for msg in messages:
        body = msg.get("body", "").strip()
        if body:
            first_line = body.split("\n")[0].strip()
            if len(first_line) > 5:
                topic = first_line[:100]
                break

    # Extract email addresses as attendees
    email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
    attendees = list(set(re.findall(email_pattern, full_text)))

    # Extract duration
    duration = 30
    duration_patterns = [
        r'(\d+)\s*min(?:ute)?s?',
        r'(\d+)\s*hour',
        r'(\d+)\s*h',
    ]
    for pattern in duration_patterns:
        match = re.search(pattern, full_text, re.IGNORECASE)
        if match:
            val = int(match.group(1))
            if 'hour' in pattern or 'h' in pattern:
                duration = val * 60
            else:
                duration = val
            break

    # Extract proposed times using the natural language parser
    today = dt.date.today()
    proposed_times = _parse_natural_date(full_text, today)

    return {
        "proposed_times": proposed_times[:5],
        "attendees": attendees,
        "topic": topic,
        "duration_minutes": duration,
    }


def parse_meeting_request(thread: dict) -> dict:
    """Use Gemini to extract meeting details from an email thread.

    Falls back to regex-based parsing if Gemini API is rate-limited.
    Uses a two-pass Gemini strategy: first tries to get only confirmed
    times; if that yields nothing, falls back to getting all mentioned times.

    Parameters
    ----------
    thread : dict
        Must contain a ``"messages"`` key whose value is a list of dicts,
        each with keys ``"from"``, ``"date"``, and ``"body"``.

    Returns
    -------
    dict
        ``{"proposed_times": [...], "attendees": [...], "topic": "...", "duration_minutes": N}``
    """
    import datetime as dt

    try:
        from google import genai
    except ImportError:
        return _parse_meeting_with_regex(thread)

    messages = thread.get("messages", [])
    if not messages:
        return {
            "parsing_error": "thread has no messages",
            "raw": "",
        }

    parts = []
    for msg in messages:
        sender = msg.get("from", "unknown")
        date = msg.get("date", "")
        body = msg.get("body", "")
        parts.append(f"[{date}] {sender}:\n{body}")

    thread_text = "\n\n---\n\n".join(parts)
    today = dt.date.today().isoformat()

    # ── Pass 1: strict — only confirmed/agreed times ─────────────────────────
    strict_prompt = (
        "You are a meeting-scheduler assistant. "
        "Extract meeting details from the email thread below.\n\n"
        "Return ONLY valid JSON. No markdown, no code fences, no extra text.\n\n"
        "The JSON must have exactly these keys:\n"
        '  "proposed_times": list of ISO-8601 datetime strings for the '
        "meeting time(s) the participants have CONFIRMED or AGREED UPON "
        "(ignore times that were merely proposed or offered as options). "
        "Resolve relative dates like 'tomorrow' or "
        f"'next Monday' using today's date: {today}. "
        "If the respondent selected one specific time (e.g. "
        "\"Thursday at 7 PM works for me\"), return ONLY that time, "
        "not the other options that were offered;\n"
        '  "attendees": list of email addresses mentioned as participants;\n'
        '  "topic": a one-line summary of what the meeting is about;\n'
        '  "duration_minutes": integer (default 30 if not specified).\n\n'
        "If you cannot determine any of these, use empty lists / sensible defaults."
    )

    prompt = f"{strict_prompt}\n\nEmail thread:\n\n{thread_text}"

    try:
        raw = _call_gemini_with_retry(prompt, model="gemini-2.5-flash")
        data = _parse_gemini_response(raw)
        if data and isinstance(data, dict):
            proposed = data.get("proposed_times", [])
            if isinstance(proposed, list) and len(proposed) > 0:
                result = {
                    "proposed_times": proposed,
                    "attendees": data.get("attendees", []),
                    "topic": data.get("topic", ""),
                    "duration_minutes": data.get("duration_minutes", 30),
                }
                if not isinstance(result["proposed_times"], list):
                    result["proposed_times"] = []
                if not isinstance(result["attendees"], list):
                    result["attendees"] = []
                if not isinstance(result["topic"], str):
                    result["topic"] = str(result["topic"])
                if not isinstance(result["duration_minutes"], int):
                    try:
                        result["duration_minutes"] = int(
                            result["duration_minutes"])
                    except (ValueError, TypeError):
                        result["duration_minutes"] = 30
                return result
    except Exception as exc:
        print(f"  ⚠️ Strict Gemini pass failed: {exc}")

    # ── Pass 2: broad — all mentioned times ──────────────────────────────────
    print("  ℹ️ Strict pass returned no times. Falling back to broad pass.")

    broad_prompt = (
        "You are a meeting-scheduler assistant. "
        "Extract meeting details from the email thread below.\n\n"
        "Return ONLY valid JSON. No markdown, no code fences, no extra text.\n\n"
        "The JSON must have exactly these keys:\n"
        '  "proposed_times": list of ISO-8601 datetime strings for EVERY '
        "time mentioned in the thread related to the meeting "
        "(resolve relative dates like 'tomorrow' or "
        f"'next Monday' using today's date: {today});\n"
        '  "attendees": list of email addresses mentioned as participants;\n'
        '  "topic": a one-line summary of what the meeting is about;\n'
        '  "duration_minutes": integer (default 30 if not specified).\n\n'
        "If you cannot determine any of these, use empty lists / sensible defaults."
    )

    prompt = f"{broad_prompt}\n\nEmail thread:\n\n{thread_text}"

    try:
        raw = _call_gemini_with_retry(prompt, model="gemini-2.5-flash")
        data = _parse_gemini_response(raw)
        if data and isinstance(data, dict):
            result = {
                "proposed_times": data.get("proposed_times", []),
                "attendees": data.get("attendees", []),
                "topic": data.get("topic", ""),
                "duration_minutes": data.get("duration_minutes", 30),
            }
            if not isinstance(result["proposed_times"], list):
                result["proposed_times"] = []
            if not isinstance(result["attendees"], list):
                result["attendees"] = []
            if not isinstance(result["topic"], str):
                result["topic"] = str(result["topic"])
            if not isinstance(result["duration_minutes"], int):
                try:
                    result["duration_minutes"] = int(
                        result["duration_minutes"])
                except (ValueError, TypeError):
                    result["duration_minutes"] = 30
            return result
    except Exception as exc:
        print(f"  ⚠️ Broad Gemini pass failed: {exc}")

    # ── Pass 3: regex fallback ───────────────────────────────────────────────
    print("  ℹ️ Gemini passes returned no times. Falling back to regex parser.")
    return _parse_meeting_with_regex(thread)


def check_availability(time_min: str, time_max: str) -> bool:
    """Check if the user's primary calendar is free during the given time range."""
    import datetime as dt

    try:
        def to_utc(time_str: str) -> str:
            if time_str.endswith("Z"):
                return time_str
            elif "+" in time_str or "-" in time_str[10:]:
                dt_obj = dt.datetime.fromisoformat(time_str)
                if dt_obj.tzinfo is not None:
                    dt_obj_utc = dt_obj.astimezone(dt.timezone.utc)
                    return dt_obj_utc.isoformat().replace("+00:00", "Z")
                else:
                    return time_str + "Z"
            else:
                return time_str + "Z"

        time_min = to_utc(time_min)
        time_max = to_utc(time_max)

        print(f"[DEBUG] Checking availability from {time_min} to {time_max}")

        service = _build_calendar_service()
        body = {
            "timeMin": time_min,
            "timeMax": time_max,
            "items": [{"id": "primary"}]
        }

        response = service.freebusy().query(body=body).execute()
        calendars = response.get("calendars", {})
        primary_busy = calendars.get("primary", {}).get("busy", [])

        print(f"[DEBUG] Busy periods found: {len(primary_busy)}")

        return len(primary_busy) == 0
    except Exception as e:
        print(f"[DEBUG] Exception in check_availability: {e}")
        return False


def find_free_slot(proposed_times: list, duration_minutes: int) -> str | None:
    """Find the first available time slot from a list of proposed times."""
    import datetime as dt

    print(
        f"[DEBUG] find_free_slot called with {len(proposed_times)} proposed times, duration {duration_minutes} minutes")

    for idx, time_str in enumerate(proposed_times):
        try:
            print(
                f"[DEBUG] Checking time {idx + 1}/{len(proposed_times)}: {time_str}")

            if time_str.endswith("Z"):
                start_time = dt.datetime.fromisoformat(
                    time_str.replace("Z", "+00:00"))
            else:
                start_time = dt.datetime.fromisoformat(time_str)

            end_time = start_time + dt.timedelta(minutes=duration_minutes)

            time_min = start_time.isoformat()
            time_max = end_time.isoformat()

            is_free = check_availability(time_min, time_max)

            if is_free:
                print(f"[DEBUG] Found free slot: {time_str}")
                return time_str
        except Exception as e:
            print(f"[DEBUG] Exception processing time {time_str}: {e}")
            continue

    print(
        f"[DEBUG] No free slot found among {len(proposed_times)} proposed times")
    return None


def find_alternative_slots(proposed_times: list, duration_minutes: int, num_alternatives: int = 5) -> list:
    """Find alternative time slots when all proposed times are busy."""
    import datetime as dt

    if not proposed_times:
        return []

    alternatives = []

    try:
        if proposed_times[0].endswith("Z"):
            ref_time = dt.datetime.fromisoformat(
                proposed_times[0].replace("Z", "+00:00"))
        else:
            ref_time = dt.datetime.fromisoformat(proposed_times[0])
    except:
        return []

    for hour in range(8, 19):
        if len(alternatives) >= num_alternatives:
            break

        try:
            alt_time = ref_time.replace(
                hour=hour, minute=0, second=0, microsecond=0)

            if alt_time < dt.datetime.now(alt_time.tzinfo):
                continue

            alt_time_str = alt_time.isoformat()
            if any(alt_time_str in pt for pt in proposed_times):
                continue

            end_time = alt_time + dt.timedelta(minutes=duration_minutes)
            is_free = check_availability(
                alt_time.isoformat(), end_time.isoformat())

            if is_free:
                alternatives.append(alt_time_str)
        except Exception as e:
            print(
                f"[DEBUG] Exception checking alternative slot at {hour}:00 {e}")
            continue

    return alternatives


def create_event(summary: str, start_time: str, duration_minutes: int, attendees: list, description: str = "") -> dict:
    """Create a Google Calendar event."""
    import datetime as dt

    if start_time.endswith("Z"):
        start_dt = dt.datetime.fromisoformat(start_time.replace("Z", "+00:00"))
    else:
        start_dt = dt.datetime.fromisoformat(start_time)

    end_dt = start_dt + dt.timedelta(minutes=duration_minutes)

    valid_attendees = [{"email": email}
                       for email in attendees if isinstance(email, str) and "@" in email]

    event_body = {
        "summary": summary,
        "description": description,
        "start": {
            "dateTime": start_dt.isoformat(),
            "timeZone": "UTC"
        },
        "end": {
            "dateTime": end_dt.isoformat(),
            "timeZone": "UTC"
        }
    }

    if valid_attendees:
        event_body["attendees"] = valid_attendees

    service = _build_calendar_service()
    event = service.events().insert(
        calendarId="primary",
        body=event_body,
        sendUpdates="all"
    ).execute()

    return event
