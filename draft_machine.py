import os
import sys
import time

import google.generativeai as genai
from dotenv import load_dotenv

from context_builder import assemble_context
from gcal import check_calendar_availability

# Load environment variables from .env
load_dotenv()

# Configure Gemini
API_KEY = os.getenv("GEMINI_API_KEY")
MODEL_NAME = "gemini-2.5-flash"

if API_KEY:
    genai.configure(api_key=API_KEY)

_MAX_RETRIES = 3
_RETRY_BASE_DELAY = 2.0  # seconds
_MAX_TOTAL_TIME = 30  # seconds total timeout

DRAFTING_RULES = """## Drafting Rules

Follow these constraints when writing the reply:

1. **ONE-ASK RULE**: Every email has exactly ONE clear question or ONE clear response. Do not ask multiple questions or make multiple separate asks.

2. **LENGTH CONTROL**: Match the energy of the thread. Maximum 5 sentences. Use numbered points if it helps clarity.

3. **NO AI FILLER**: Never use phrases like "I hope this finds you well", "Thank you for reaching out", "I wanted to follow up", "Just checking in", or any other generic email filler. Be direct and human.

4. **STRUCTURE**: Acknowledge briefly -> give your response -> end with ONE clear next step.

Return ONLY the reply body text. No subject line. No preamble. No explanation."""


def _build_combined_prompt(thread: dict) -> str:
    """Build the full prompt sent to Gemini by merging context + drafting rules.

    For meeting/scheduling threads, automatically fetches calendar availability
    so the AI can suggest times when you're actually free.
    """
    try:
        calendar_data = check_calendar_availability(days_ahead=7)
    except Exception:
        calendar_data = None

    context = assemble_context(thread, calendar_availability=calendar_data)
    return (
        f"{context['system']}\n\n"
        f"{DRAFTING_RULES}\n\n"
        f"{context['user']}"
    )


def _generate_with_retry(model: genai.GenerativeModel, prompt: str) -> str:
    """Call model.generate_content with exponential backoff retry for rate limits."""
    start_time = time.time()
    
    for attempt in range(_MAX_RETRIES):
        # Check if we've exceeded total timeout
        if time.time() - start_time > _MAX_TOTAL_TIME:
            raise RuntimeError(f"Timeout after {time.time() - start_time:.1f}s due to persistent rate limiting.")
        
        try:
            response = model.generate_content(prompt)
            return response.text.strip()
        except Exception as e:
            error_str = str(e)
            if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str:
                if attempt < _MAX_RETRIES - 1:
                    retry_after = min(_RETRY_BASE_DELAY * (2 ** attempt), 5.0)  # Cap at 5s
                    print(
                        f"  ⏳ Rate limited on draft (attempt {attempt + 1}/{_MAX_RETRIES}). "
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


def draft_reply(thread: dict) -> str:
    """Generate an email reply draft for the given thread.

    Args:
        thread: A dict with 'subject' (str) and 'messages' (list of
                {'from': str, 'date': str, 'body': str}).

    Returns:
        The draft text only (no subject line, no explanation).
    """
    if not API_KEY:
        raise RuntimeError(
            "GEMINI_API_KEY not found. "
            "Make sure your .env file contains GEMINI_API_KEY=your_key_here"
        )

    prompt = _build_combined_prompt(thread)
    model = genai.GenerativeModel(MODEL_NAME)
    return _generate_with_retry(model, prompt)


def draft_reply_with_metadata(thread: dict) -> dict:
    """Generate an email reply draft and return it with metadata.

    Args:
        thread: A dict with 'subject' (str) and 'messages' (list of
                {'from': str, 'date': str, 'body': str}).

    Returns:
        A dict with:
            - "draft": the reply text
            - "model": the model name used
            - "subject": the thread subject
            - "replying_to": who we're replying to (last message sender)
    """
    draft = draft_reply(thread)
    last_from = thread["messages"][-1]["from"] if thread["messages"] else "unknown"
    return {
        "draft": draft,
        "model": MODEL_NAME,
        "subject": thread["subject"],
        "replying_to": last_from,
    }


def _print_metadata(result: dict) -> None:
    """Pretty-print a metadata dict."""
    sep = "=" * 72
    print(sep)
    print("DRAFT — GENERATED")
    print(sep)
    print(f"Model:       {result['model']}")
    print(f"Subject:     {result['subject']}")
    print(f"Replying to: {result['replying_to']}")
    print(sep)
    print(result["draft"])
    print(sep)


if __name__ == "__main__":
    # Same sample thread style as context_builder.py — Q3 Budget Review
    sample_thread = {
        "subject": "Q3 Budget Review — final approval needed",
        "messages": [
            {
                "from": "Meera (Finance)",
                "date": "2026-07-09",
                "body": (
                    "Hi Rahul,\n\n"
                    "All department heads have submitted their Q3 budget proposals. "
                    "Could you review and sign off by end of week? "
                    "We're especially tight on the engineering growth line item — "
                    "it's 15% over projection.\n\n"
                    "I've attached the summary spreadsheet for reference.\n\n"
                    "Thanks,\nMeera"
                ),
            },
            {
                "from": "Vikram (VP Product)",
                "date": "2026-07-09",
                "body": (
                    "+1 on Meera's note. I'd like to understand the eng growth "
                    "overage before we approve. Rahul, can we chat through it "
                    "before you sign?\n\n"
                    "Vikram"
                ),
            },
        ],
    }

    if not API_KEY:
        print("ERROR: GEMINI_API_KEY not found in .env file.")
        print()
        print("To fix this, add the following line to your .env file:")
        print("  GEMINI_API_KEY=your_actual_key_here")
        print()
        print("Then re-run this script.")
        sys.exit(1)

    try:
        result = draft_reply_with_metadata(sample_thread)
        _print_metadata(result)
    except Exception as e:
        print(f"ERROR: Failed to generate draft — {e}")
        sys.exit(1)
