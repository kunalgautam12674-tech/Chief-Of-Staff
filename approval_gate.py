"""
approval_gate.py — Human-in-the-Loop approval gate for AI email ghostwriter.

Provides a Streamlit UI where the user:
  1. Selects or pastes an email thread
  2. Generates an AI draft reply
  3. Approves / Edits / Rejects before anything is sent

Key principle: NEVER auto-send without human approval.
"""

import json
import os
from datetime import datetime
from pathlib import Path

import streamlit as st

from context_builder import assemble_context, format_thread_history
from draft_machine import draft_reply, draft_reply_with_metadata

# ---------------------------------------------------------------------------
# Sample threads
# ---------------------------------------------------------------------------
SAMPLE_THREADS = [
    {
        "label": "Q3 Budget Review — final approval needed",
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
    },
    {
        "label": "Launch date for the new reporting module",
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
    },
    {
        "label": "Vendor contract renewal — feedback requested",
        "subject": "Vendor contract renewal — feedback requested",
        "messages": [
            {
                "from": "Sneha (Procurement)",
                "date": "2026-07-10",
                "body": (
                    "Hi Rahul,\n\n"
                    "Our contract with DataSync Pro is up for renewal next month. "
                    "They're proposing a 12% increase for the enterprise tier. "
                    "I've negotiated them down to 7%, but I'd like your input "
                    "before I sign.\n\n"
                    "Key changes:\n"
                    "1. 5 TB → 10 TB data allowance\n"
                    "2. 24/7 support included\n"
                    "3. 2-year lock-in for the reduced rate\n\n"
                    "Worth it?\n\n"
                    "Best,\nSneha"
                ),
            },
            {
                "from": "Ravi (Engineering)",
                "date": "2026-07-10",
                "body": (
                    "From eng's side, DataSync Pro has been solid. "
                    "The 24/7 support would have saved us last quarter "
                    "when that pipeline went down over the weekend.\n\n"
                    "I'd say go for it.\n\n"
                    "Ravi"
                ),
            },
        ],
    },
]

APPROVED_DRAFTS_PATH = Path("approved_drafts.json")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_approved_drafts() -> list:
    """Load existing approved drafts from JSON file."""
    if APPROVED_DRAFTS_PATH.exists():
        with open(APPROVED_DRAFTS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def _save_approved_draft(draft_data: dict) -> None:
    """Append a draft record to approved_drafts.json."""
    drafts = _load_approved_drafts()
    drafts.append(draft_data)
    with open(APPROVED_DRAFTS_PATH, "w", encoding="utf-8") as f:
        json.dump(drafts, f, indent=2, ensure_ascii=False)


def _resolve_api_key() -> str | None:
    """Resolve GROQ_API_KEY from st.secrets → os.environ → None."""
    try:
        return st.secrets.get("GROQ_API_KEY", os.environ.get("GROQ_API_KEY"))
    except Exception:
        return os.environ.get("GROQ_API_KEY")


def _render_thread(thread: dict) -> str:
    """Render a thread dict as readable HTML for the left column."""
    parts = [f"<h3>Subject: {thread['subject']}</h3>"]
    for msg in thread["messages"]:
        parts.append(
            f'<div class="thread-message">'
            f'<div class="msg-header"><strong>{msg["from"]}</strong> &middot; {msg["date"]}</div>'
            f'<div class="msg-body">{msg["body"].replace(chr(10), "<br>")}</div>'
            f"</div>"
        )
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Page config & styling
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="AI Email Ghostwriter — Approval Gate",
    page_icon="✍️",
    layout="wide",
)

st.markdown(
    """
<style>
    /* Dark theme base */
    .stApp {
        background-color: #1a1a2e;
        color: #e0e0e0;
    }
    .stApp header { background-color: #16213e; }
    .stApp [data-testid="stSidebar"] {
        background-color: #16213e;
    }
    .stApp [data-testid="stSidebar"] .stSelectbox label,
    .stApp [data-testid="stSidebar"] .stTextArea label {
        color: #e0e0e0;
    }

    /* Thread message boxes */
    .thread-message {
        background: #16213e;
        border: 1px solid #0f3460;
        border-radius: 8px;
        padding: 12px 16px;
        margin-bottom: 12px;
    }
    .msg-header {
        color: #e94560;
        font-size: 0.9rem;
        margin-bottom: 6px;
    }
    .msg-body {
        color: #d0d0d0;
        line-height: 1.5;
        font-size: 0.95rem;
    }

    /* Draft display box */
    .draft-box {
        background: #16213e;
        border: 1px solid #0f3460;
        border-radius: 8px;
        padding: 16px 20px;
        margin-top: 8px;
        color: #e0e0e0;
        line-height: 1.6;
        font-size: 1rem;
        white-space: pre-wrap;
    }

    /* Status indicators */
    .status-approved {
        background: #1b4332;
        border: 1px solid #2d6a4f;
        color: #95d5b2;
        padding: 10px 16px;
        border-radius: 8px;
        font-weight: 600;
        text-align: center;
        margin-top: 12px;
    }
    .status-rejected {
        background: #4a1a1a;
        border: 1px solid #8b2d2d;
        color: #f5a5a5;
        padding: 10px 16px;
        border-radius: 8px;
        font-weight: 600;
        text-align: center;
        margin-top: 12px;
    }

    /* Buttons row */
    .action-buttons {
        display: flex;
        gap: 12px;
        margin-top: 20px;
    }

    /* Override Streamlit button colours */
    div[data-testid="stButton"] button[kind="primary"] {
        background-color: #2d6a4f;
        border-color: #2d6a4f;
        color: white;
    }
    div[data-testid="stButton"] button[kind="secondary"] {
        border-color: #e94560;
        color: #e94560;
    }

    /* Headings */
    h1, h2, h3 {
        color: #e0e0e0;
    }
    h3 {
        margin-bottom: 16px;
        border-bottom: 1px solid #0f3460;
        padding-bottom: 8px;
    }

    /* Text area styling */
    .stTextArea textarea {
        background-color: #16213e;
        color: #e0e0e0;
        border: 1px solid #0f3460;
        border-radius: 8px;
    }
</style>
""",
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Initialise session state
# ---------------------------------------------------------------------------

if "draft" not in st.session_state:
    st.session_state.draft = ""
if "status" not in st.session_state:
    st.session_state.status = "none"  # none | approved | editing | rejected
if "selected_thread" not in st.session_state:
    st.session_state.selected_thread = None
if "generation_count" not in st.session_state:
    st.session_state.generation_count = 0
if "edited_text" not in st.session_state:
    st.session_state.edited_text = ""
if "last_thread_key" not in st.session_state:
    st.session_state.last_thread_key = None

# ---------------------------------------------------------------------------
# Sidebar — thread selection
# ---------------------------------------------------------------------------

st.sidebar.title("✍️ Email Ghostwriter")
st.sidebar.markdown("---")

# API key check
api_key = _resolve_api_key()
if not api_key:
    st.sidebar.warning("GROQ_API_KEY not found", icon="🔑")
    user_key = st.sidebar.text_input(
        "Enter your GROQ API key:",
        type="password",
        help="Your key is used only for this session and is not stored.",
    )
    if user_key:
        os.environ["GROQ_API_KEY"] = user_key
        api_key = user_key
        st.sidebar.success("API key set for this session.")
    else:
        st.sidebar.info(
            "Add GROQ_API_KEY to Streamlit secrets or your .env file to persist."
        )
else:
    st.sidebar.success("✅ API key configured")

st.sidebar.markdown("---")
st.sidebar.header("📬 Thread Selection")

# Dropdown for sample threads
thread_labels = [t["label"] for t in SAMPLE_THREADS]
selected_label = st.sidebar.selectbox(
    "Choose a sample thread:",
    [""] + thread_labels,
    key="thread_selector",
)

# Text area for custom thread JSON
st.sidebar.markdown("**— or —**")
custom_json = st.sidebar.text_area(
    "Paste custom thread JSON:",
    height=200,
    placeholder=(
        '{\n'
        '  "subject": "...",\n'
        '  "messages": [\n'
        '    {"from": "...", "date": "...", "body": "..."}\n'
        '  ]\n'
        '}'
    ),
    key="custom_thread_json",
)

# Resolve which thread to use
resolved_thread = None
if custom_json.strip():
    try:
        resolved_thread = json.loads(custom_json.strip())
        if "subject" not in resolved_thread or "messages" not in resolved_thread:
            st.sidebar.error(
                "JSON must contain 'subject' and 'messages' keys.")
            resolved_thread = None
    except json.JSONDecodeError as e:
        st.sidebar.error(f"Invalid JSON: {e}")
        resolved_thread = None
elif selected_label:
    resolved_thread = next(
        t for t in SAMPLE_THREADS if t["label"] == selected_label
    )

# Generate Draft button
gen_disabled = resolved_thread is None
generate_clicked = st.sidebar.button(
    "🚀 Generate Draft",
    type="primary",
    use_container_width=True,
    disabled=gen_disabled,
)

# ---------------------------------------------------------------------------
# Main area — two-column layout
# ---------------------------------------------------------------------------

st.title("✍️ AI Email Ghostwriter")
st.markdown(
    '<p style="color: #a0a0a0; margin-top: -12px;">'
    "Review & approve every draft before it's sent. "
    "Never auto-send without human approval.</p>",
    unsafe_allow_html=True,
)
st.markdown("---")

# Handle Generate Draft
if generate_clicked and resolved_thread:
    with st.spinner("Generating draft..."):
        try:
            result = draft_reply_with_metadata(resolved_thread)
            st.session_state.draft = result["draft"]
            st.session_state.status = "none"
            st.session_state.selected_thread = resolved_thread
            st.session_state.generation_count += 1
            st.session_state.edited_text = ""
            st.session_state.last_thread_key = json.dumps(
                resolved_thread, sort_keys=True, default=str
            )
        except Exception as e:
            st.error(f"Failed to generate draft: {e}")
            st.session_state.draft = ""
            st.session_state.status = "none"

# If we have a selected thread, show the two-column layout
if st.session_state.selected_thread:
    col_left, col_right = st.columns(2)

    # --- LEFT COLUMN: Thread history ---
    with col_left:
        st.subheader("📜 Thread History")
        thread_html = _render_thread(st.session_state.selected_thread)
        st.markdown(thread_html, unsafe_allow_html=True)

    # --- RIGHT COLUMN: Draft & actions ---
    with col_right:
        st.subheader("🤖 AI-Generated Draft")

        if st.session_state.status == "none" and st.session_state.draft:
            # Show the draft
            st.markdown(
                f'<div class="draft-box">{st.session_state.draft}</div>',
                unsafe_allow_html=True,
            )

            # Action buttons
            st.markdown('<div class="action-buttons">', unsafe_allow_html=True)
            a_col1, a_col2, a_col3 = st.columns(3)

            with a_col1:
                if st.button("✅ Approve", type="primary", use_container_width=True):
                    st.session_state.status = "approved"
                    record = {
                        "approved_at": datetime.now().isoformat(),
                        "subject": st.session_state.selected_thread["subject"],
                        "draft": st.session_state.draft,
                        "generation": st.session_state.generation_count,
                    }
                    _save_approved_draft(record)

            with a_col2:
                if st.button("✏️ Edit", use_container_width=True):
                    st.session_state.status = "editing"
                    st.session_state.edited_text = st.session_state.draft

            with a_col3:
                if st.button("🗑️ Reject", use_container_width=True):
                    st.session_state.status = "rejected"

            st.markdown("</div>", unsafe_allow_html=True)

        elif st.session_state.status == "approved":
            st.markdown(
                f'<div class="draft-box">{st.session_state.draft}</div>',
                unsafe_allow_html=True,
            )
            st.markdown(
                '<div class="status-approved">✅ Approved & saved to approved_drafts.json</div>',
                unsafe_allow_html=True,
            )
            if st.button("🔄 Generate New Draft", use_container_width=True):
                st.session_state.status = "none"
                st.session_state.draft = ""
                st.rerun()

        elif st.session_state.status == "editing":
            st.markdown("**Edit the draft below, then approve:**")
            edited = st.text_area(
                "Edit draft:",
                value=st.session_state.edited_text,
                height=250,
                key="edit_area",
            )
            st.session_state.edited_text = edited

            e_col1, e_col2 = st.columns(2)
            with e_col1:
                if st.button("✅ Approve Edited Version", type="primary", use_container_width=True):
                    st.session_state.draft = st.session_state.edited_text
                    st.session_state.status = "approved"
                    record = {
                        "approved_at": datetime.now().isoformat(),
                        "subject": st.session_state.selected_thread["subject"],
                        "draft": st.session_state.draft,
                        "generation": st.session_state.generation_count,
                        "edited": True,
                    }
                    _save_approved_draft(record)
                    st.rerun()
            with e_col2:
                if st.button("↩️ Cancel Edit", use_container_width=True):
                    st.session_state.status = "none"
                    st.rerun()

        elif st.session_state.status == "rejected":
            st.markdown(
                f'<div class="draft-box">{st.session_state.draft}</div>',
                unsafe_allow_html=True,
            )
            st.markdown(
                '<div class="status-rejected">❌ Draft rejected</div>',
                unsafe_allow_html=True,
            )
            if st.button("🔄 Regenerate Draft", type="primary", use_container_width=True):
                st.session_state.status = "none"
                st.session_state.draft = ""
                st.rerun()

        else:
            st.info(
                "Select a thread from the sidebar and click "
                "**🚀 Generate Draft** to get started."
            )

else:
    # No thread selected yet
    st.info(
        "👈 Select a sample thread from the sidebar, or paste custom thread JSON, "
        "then click **🚀 Generate Draft**."
    )

# ---------------------------------------------------------------------------
# Footer
# ---------------------------------------------------------------------------

st.markdown("---")
st.markdown(
    '<p style="text-align: center; color: #666; font-size: 0.8rem;">'
    "🔒 Human-in-the-loop guardrail active — nothing is sent without your approval."
    "</p>",
    unsafe_allow_html=True,
)
