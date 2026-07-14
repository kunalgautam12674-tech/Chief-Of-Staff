import os
import time
from google import genai
from google.genai import errors


def load_env():
    """Load .env file manually without requiring python-dotenv."""
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, val = line.partition("=")
                    os.environ.setdefault(key.strip(), val.strip())


load_env()

api_key = os.environ.get("GEMINI_API_KEY")
if not api_key:
    raise ValueError(
        "No API key found. Set GEMINI_API_KEY in .env file "
        "or as an environment variable."
    )
client = genai.Client(api_key=api_key)
MODEL = "gemini-3.1-flash-lite"  # fast, cheap, good for triage

# Free tier rate limit: 15 requests per minute → 4s minimum spacing
_RATE_LIMIT_DELAY = 4.0  # seconds between calls to stay under 15/min
_MAX_RETRIES = 3
_MAX_TOTAL_TIME = 30  # seconds total timeout


def _call_with_retry(prompt: str, delay: float = _RATE_LIMIT_DELAY) -> str:
    """Call Gemini with exponential backoff retry for 429 rate limits."""
    start_time = time.time()
    
    for attempt in range(_MAX_RETRIES):
        # Check if we've exceeded total timeout
        if time.time() - start_time > _MAX_TOTAL_TIME:
            raise RuntimeError(f"Timeout after {time.time() - start_time:.1f}s due to persistent rate limiting.")
        
        try:
            response = client.models.generate_content(
                model=MODEL,
                contents=prompt,
            )
            return response.text
        except errors.ClientError as e:
            if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                if attempt < _MAX_RETRIES - 1:
                    # Parse retry delay from error message, or use exponential backoff
                    retry_after = min(delay * (2 ** attempt), 5.0)  # Cap at 5s
                    print(
                        f"  ⏳ Rate limited (attempt {attempt + 1}/{_MAX_RETRIES}). "
                        f"Retrying in {retry_after:.1f}s..."
                    )
                    time.sleep(retry_after)
                else:
                    raise RuntimeError(
                        f"Failed after {_MAX_RETRIES} retries due to persistent rate limiting. The Gemini API may be rate-limited. Please try again in a few minutes."
                    )
            else:
                raise
    raise RuntimeError(
        f"Failed after {_MAX_RETRIES} retries due to persistent rate limiting."
    )


def triage_thread(sender: str, subject: str, snippet: str) -> dict:
    prompt = f"""
        You are an intelligent email assistant helping triage an inbox.

        Given this email thread metadata, classify it:

        Sender: {sender}
        Subject: {subject}
        Preview: {snippet}

        Respond in this exact format:
        Priority: <urgent | needs-reply | fyi | ignore>
        Category: <one short tag like: meeting-request, follow-up, newsletter, billing, job-app, social, admin, other>
        Reason: <one sentence explaining why>
        """

    text = _call_with_retry(prompt)
    return parse_triage_response(text)


def parse_triage_response(text: str) -> dict:
    result = {"priority": "unknown", "category": "other", "reason": ""}

    for line in text.strip().split("\n"):
        if line.startswith("Priority:"):
            result["priority"] = line.replace("Priority:", "").strip().lower()
        elif line.startswith("Category:"):
            result["category"] = line.replace("Category:", "").strip().lower()
        elif line.startswith("Reason:"):
            result["reason"] = line.replace("Reason:", "").strip()

    return result


def triage_inbox(threads: list, progress_callback=None) -> list:
    """Triage all threads, with optional progress callback for UI updates.

    Parameters
    ----------
    threads : list
        List of dicts with 'sender', 'subject', 'snippet'.
    progress_callback : callable, optional
        Called as ``progress_callback(current, total, subject)`` after each
        thread is triaged, to support progress bars in the UI.

    Returns
    -------
    list
        Threads with priority/category/reason added, sorted by priority.
    """
    triaged = []

    for i, thread in enumerate(threads):
        subject = thread.get("subject", "(no subject)")
        if progress_callback:
            progress_callback(i + 1, len(threads), subject)

        label = triage_thread(
            sender=thread["sender"],
            subject=subject,
            snippet=thread.get("snippet", ""),
        )
        triaged.append({**thread, **label})

        # Rate limiting: sleep between calls to stay under free tier quota
        if i < len(threads) - 1:
            time.sleep(_RATE_LIMIT_DELAY)

    # Sort by priority
    priority_order = {"urgent": 0, "needs-reply": 1,
                      "fyi": 2, "ignore": 3, "unknown": 4}
    triaged.sort(key=lambda x: priority_order.get(x["priority"], 4))

    return triaged


if __name__ == "__main__":
    sample_threads = [
        {"sender": "boss@company.com", "subject": "Need your input by EOD",
            "snippet": "Can you review the attached proposal before 5pm?"},
        {"sender": "newsletter@medium.com", "subject": "Top stories for you this week",
            "snippet": "Here's what's trending in tech..."},
        {"sender": "recruiter@startup.io", "subject": "Quick call this week?",
            "snippet": "Hi, I came across your profile and wanted to connect..."},
    ]

    results = triage_inbox(sample_threads)

    for r in results:
        print(
            f"[{r['priority'].upper()}] [{r['category']}] {r['subject']} \u2014 {r['reason']}")
