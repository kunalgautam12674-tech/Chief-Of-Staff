"""
engine.py - Gmail thread fetching using the Google Gmail API directly.

Provides fetch_threads() which returns the last 20 inbox threads
as a list of dicts with keys: thread_id, sender, subject, snippet, date.

Uses the existing OAuth credentials from the Gmail MCP server's config.
"""

import json
import os
import re
from pathlib import Path
from triage import triage_inbox

# We need google-auth-oauthlib and google-api-python-client
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

# ── Helpers ──────────────────────────────────────────────────────────────────

SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.settings.basic",
    "https://www.googleapis.com/auth/calendar",
]

_CONFIG_DIR = Path(os.path.expanduser("~")) / ".gmail-mcp"
_OAUTH_KEYS_PATH = _CONFIG_DIR / "gcp-oauth.keys.json"
_CREDENTIALS_PATH = _CONFIG_DIR / "credentials.json"


def _get_authenticated_service():
    """Load or refresh credentials and return a Gmail API service object.

    The Gmail MCP server saves the token file (``credentials.json``) in a
    Google "authorized user" format that lacks ``client_id`` / ``client_secret``.
    We therefore read those from the OAuth keys file and merge them.
    """
    if not _OAUTH_KEYS_PATH.exists():
        raise FileNotFoundError(
            f"OAuth keys not found. Place gcp-oauth.keys.json "
            f"in {_CONFIG_DIR}"
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
        # google.oauth2.credentials.Credentials accepts these fields directly
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
            print("Refreshing expired Gmail token...")
            creds.refresh(Request())
        else:
            # Run the OAuth flow (opens a browser)
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

    return build("gmail", "v1", credentials=creds)


def _parse_expiry(expiry_date):
    """Convert a millisecond timestamp (from the old credentials.json) to a
    naive UTC datetime (as google.auth expects internally), or return None."""
    if expiry_date:
        import datetime
        try:
            return datetime.datetime.fromtimestamp(expiry_date / 1000, tz=datetime.timezone.utc).replace(tzinfo=None)
        except Exception:
            pass
    return None


def _get_header(headers, name: str) -> str:
    """Get a header value by name (case-insensitive)."""
    name_lower = name.lower()
    for h in headers:
        if h.get("name", "").lower() == name_lower:
            return h.get("value", "")
    return ""


def _extract_snippet(payload: dict, max_chars: int = 200) -> str:
    """Extract a plain-text snippet from the MIME payload, max *max_chars*."""
    parts = [payload]

    text_parts: list[str] = []
    while parts:
        part = parts.pop(0)
        mime = part.get("mimeType", "")
        data = part.get("body", {}).get("data")

        if data:
            import base64
            decoded = base64.urlsafe_b64decode(
                data).decode("utf-8", errors="replace")
            if mime == "text/plain":
                text_parts.append(decoded)
            elif mime == "text/html" and not text_parts:
                # Only use HTML if we have no plain text
                text_parts.append(re.sub(r"<[^>]+>", "", decoded))

        sub_parts = part.get("parts", [])
        if sub_parts:
            parts.extend(sub_parts)

    snippet = " ".join(text_parts).strip()
    # Collapse whitespace
    snippet = re.sub(r"\s+", " ", snippet)

    if len(snippet) > max_chars:
        snippet = snippet[:max_chars].rsplit(" ", 1)[0] + " …"

    return snippet


# ── Public API ───────────────────────────────────────────────────────────────


def send_reply(
    thread_id: str,
    reply_body: str,
    to: str,
    subject: str,
    references: str = "",
    in_reply_to: str = "",
    cc: str = "",
    bcc: str = "",
) -> dict:
    """Send an email as a reply to an existing Gmail thread.

    Constructs the RFC 2822 message with proper threading headers
    (``In-Reply-To`` and ``References``) so that Gmail nests the reply
    inside the original thread.

    Parameters
    ----------
    thread_id : str
        The Gmail ``threadId`` to reply to.
    reply_body : str
        Plain-text body of the reply.
    to : str
        Recipient email address(es), comma-separated if multiple.
    subject : str
        Subject line (typically ``"Re: …"`` but the caller should provide
        the full subject they want).
    references : str
        The ``Message-ID`` of the original message, optionally with
        earlier ``Message-ID``\\ s space-separated.  Used for the
        ``References`` header.
    in_reply_to : str
        The ``Message-ID`` of the immediate message being replied to.
        Used for the ``In-Reply-To`` header.
    cc : str
        CC recipient(s), comma-separated.
    bcc : str
        BCC recipient(s), comma-separated.

    Returns
    -------
    dict
        The Gmail API response from ``messages.send()``, which includes
        ``id``, ``threadId``, and ``labelIds``.

    Raises
    ------
    googleapiclient.errors.HttpError
        If the API call fails (e.g. invalid thread, auth error).
    """
    import base64
    from email.mime.text import MIMEText

    service = _get_authenticated_service()

    # Build a MIMEText message
    msg = MIMEText(reply_body)
    msg["To"] = to
    msg["Subject"] = subject

    if cc:
        msg["Cc"] = cc
    if bcc:
        msg["Bcc"] = bcc

    # Threading headers — these tell Gmail to nest this reply in the thread
    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to
    if references:
        msg["References"] = references

    # Base64url-encode the raw message
    raw_bytes = msg.as_bytes()
    encoded = base64.urlsafe_b64encode(raw_bytes).decode("ascii")

    body = {"raw": encoded, "threadId": thread_id}

    sent = (
        service.users()
        .messages()
        .send(userId="me", body=body)
        .execute()
    )
    return sent


def fetch_threads(max_results: int = 5) -> list[dict]:
    """Fetch the last *max_results* inbox threads via the Gmail API.

    Returns
    -------
    list[dict]
        Each dict has keys:
        - thread_id  : str – Gmail thread ID
        - sender     : str – From header
        - subject    : str – Subject header
        - snippet    : str – first ~200 chars of the email body
        - date       : str – Date header
    """
    service = _get_authenticated_service()

    # 1. List messages in inbox
    results = (
        service.users()
        .messages()
        .list(userId="me", q="in:inbox", maxResults=max_results)
        .execute()
    )

    messages = results.get("messages", [])
    if not messages:
        return []

    # 2. Get full details for each message
    threads: list[dict] = []
    for msg in messages:
        try:
            detail = (
                service.users()
                .messages()
                .get(userId="me", id=msg["id"], format="full")
                .execute()
            )
        except Exception:
            continue

        headers = detail.get("payload", {}).get("headers", [])
        thread_id = detail.get("threadId", "")
        message_id = detail.get("id", "")
        sender = _get_header(headers, "From")
        subject = _get_header(headers, "Subject")
        date = _get_header(headers, "Date")
        snippet = _extract_snippet(detail.get("payload", {}))
        references = _get_header(headers, "References")
        in_reply_to = _get_header(headers, "In-Reply-To")
        # If no References header exists, use the message's own Message-ID
        msg_id_header = _get_header(headers, "Message-ID")
        if not references and msg_id_header:
            references = msg_id_header

        if thread_id and sender:
            threads.append({
                "thread_id": thread_id,
                "message_id": message_id,
                "sender": sender,
                "subject": subject,
                "snippet": snippet,
                "date": date,
                "references": references,
                "in_reply_to": in_reply_to,
                "msg_id_header": msg_id_header,
            })

    return threads


# ── Digested Output ──────────────────────────────────────────────────────────


def format_digest(results: list[dict]) -> None:
    """Print a clean, readable inbox digest grouped by priority.

    Parameters
    ----------
    results : list[dict]
        The triaged thread list (already sorted by priority via triage_inbox).
    """
    from datetime import date

    today = date.today().isoformat()
    total = len(results)

    print(f"{'=' * 60}")
    print(
        f"  INBOX DIGEST  —  {today}  |  {total} thread{'s' if total != 1 else ''}")
    print(f"{'=' * 60}\n")

    if not results:
        print("  (no threads to display)")
        return

    priority_order = ["urgent", "needs-reply", "fyi", "ignore", "unknown"]
    prev_priority = None

    for thread in results:
        priority = thread.get("priority", "unknown")
        sender = thread.get("sender", "")
        subject = thread.get("subject", "")
        reason = thread.get("reason", "")

        # Print a separator line between priority groups
        if priority != prev_priority and prev_priority is not None:
            print(f"{'-' * 60}\n")
        prev_priority = priority

        print(
            f"  [{priority.upper()}] {sender} | {subject} — {reason}"
        )

    print()


def run_pipeline(max_results: int = 5) -> list[dict]:
    """Run the full fetch → triage → digest pipeline.

    Parameters
    ----------
    max_results : int
        Number of inbox threads to fetch (default 5).

    Returns
    -------
    list[dict]
        The fully triaged and sorted thread list.
    """
    threads = fetch_threads(max_results=max_results)
    results = triage_inbox(threads)
    format_digest(results)
    return results


# ── CLI entry point ──────────────────────────────────────────────────────────


if __name__ == "__main__":
    run_pipeline()
