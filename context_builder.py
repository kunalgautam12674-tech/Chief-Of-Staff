import json
import re

# Meeting-related keywords to detect scheduling/meeting threads
_MEETING_KEYWORDS = [
    "meet", "meeting", "schedule", "calend", "call", "quick chat",
    "sync", "catch up", "free", "available", "availability",
    "book", "slot", "time slot", "when works", "coffee",
    "standup", "stand-up", "1:1", "one-on-one", "discuss",
    "get together", "connect", "hop on", "jump on",
]


def _is_meeting_thread(thread: dict) -> bool:
    """Detect if a thread is about scheduling a meeting/call based on subject + message bodies."""
    text = thread.get("subject", "").lower()
    for msg in thread.get("messages", []):
        text += " " + msg.get("body", "").lower()
    return any(re.search(rf"\b{kw}\b", text) for kw in _MEETING_KEYWORDS)


def load_tone_profile(path="tone_profile.json") -> dict:
    """Reads and returns the tone profile dict from a JSON file."""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_past_replies(path="past_replies.json") -> list:
    """Reads and returns a list of past reply examples from a JSON file."""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def format_thread_history(thread: dict) -> str:
    """Takes a thread dict with 'subject' and 'messages' (list of {from, date, body})
    and formats it as a readable string showing who said what in order."""
    lines = [f"Subject: {thread['subject']}", ""]
    for msg in thread["messages"]:
        lines.append(f"From: {msg['from']}")
        lines.append(f"Date: {msg['date']}")
        lines.append(f"Body:\n{msg['body']}")
        lines.append("---")
    return "\n".join(lines).strip()


def build_system_prompt(tone_profile: dict, past_replies: list) -> str:
    """Builds the system prompt that includes the persona, writing rules,
    and 2-3 past reply examples formatted as 'Here's how {name} writes:'."""
    name = tone_profile["name"]
    role = tone_profile["role"]
    tone = tone_profile["tone"]
    formality = tone_profile["formality"]
    quirks = tone_profile["quirks"]
    signature = tone_profile["signature"]

    sections = [
        f"You are {name}, a {role}. You write in a {tone} tone with {formality} formality.",
        "",
        "Writing rules:",
    ]
    for i, quirk in enumerate(quirks, 1):
        sections.append(f"{i}. {quirk}")
    sections.append("")

    # Include up to 3 past reply examples
    sections.append(f"Here's how {name} writes:")
    sections.append("")
    for reply in past_replies[:3]:
        sections.append(f"--- Example: {reply['subject']} ---")
        sections.append(reply["body"])
        sections.append("")

    sections.append(f"Always sign off with: {signature}")
    sections.append("")
    sections.append(
        "Write the reply in the first person as this person. Match their voice, "
        "structure, and level of formality exactly."
    )

    return "\n".join(sections)


def build_user_prompt(thread_formatted: str) -> str:
    """Builds the user message asking for a reply draft."""
    return (
        "Below is the email thread I need to reply to. "
        "Please draft a reply in my voice, following the writing style guidelines above.\n\n"
        f"--- Thread ---\n{thread_formatted}\n\n"
        "Please write the reply now."
    )


def assemble_context(
    thread: dict,
    tone_path: str = "tone_profile.json",
    replies_path: str = "past_replies.json",
    calendar_availability: str | None = None,
) -> dict:
    """The main function that loads everything and returns a dict
    with 'system' and 'user' prompts.

    Parameters
    ----------
    thread : dict
        The thread dict with 'subject' and 'messages'.
    tone_path : str
        Path to the tone profile JSON file.
    replies_path : str
        Path to the past replies JSON file.
    calendar_availability : str | None
        If provided, a human-readable summary of calendar free/busy
        that will be injected into the user prompt for meeting threads.

    Returns
    -------
    dict
        With keys 'system' and 'user'.
    """
    tone_profile = load_tone_profile(tone_path)
    past_replies = load_past_replies(replies_path)
    thread_formatted = format_thread_history(thread)
    system_prompt = build_system_prompt(tone_profile, past_replies)
    user_prompt = build_user_prompt(thread_formatted)

    # If this is a meeting/scheduling thread and we have calendar data, inject it
    if calendar_availability and _is_meeting_thread(thread):
        user_prompt += (
            "\n\n"
            "--- Calendar Availability ---\n"
            f"{calendar_availability}\n\n"
            "The above is your current calendar. When suggesting times for a meeting "
            "or responding to a scheduling request, use this information to propose "
            "times when you are actually free. If the sender proposed specific times, "
            "check them against your calendar and confirm or suggest alternatives."
        )

    return {"system": system_prompt, "user": user_prompt}


if __name__ == "__main__":
    sample_thread = {
        "subject": "Launch date for the new reporting module",
        "messages": [
            {
                "from": "Priya (Engineering)",
                "date": "2026-07-08",
                "body": (
                    "Hi Rahul,\n\n"
                    "We've finished the backend work for the reporting module. "
                    "Can we target a July 20 launch? There are a few edge cases "
                    "we're still testing, but I think it's realistic.\n\n"
                    "Let me know if that timeline works for you.\n\n"
                    "Cheers,\nPriya"
                ),
            },
            {
                "from": "Ankit (Design)",
                "date": "2026-07-09",
                "body": (
                    "Hey team,\n\n"
                    "From design's side, we're good to go. The UI mockups are finalised "
                    "and handed off. No blockers on our end.\n\n"
                    "Ankit"
                ),
            },
        ],
    }

    context = assemble_context(sample_thread)

    print("=" * 72)
    print("SYSTEM PROMPT")
    print("=" * 72)
    print(context["system"])
    print()
    print("=" * 72)
    print("USER PROMPT")
    print("=" * 72)
    print(context["user"])
