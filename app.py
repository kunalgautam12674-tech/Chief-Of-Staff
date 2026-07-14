"""
app.py — The Draft Desk
Unified Streamlit front-end for the AI Chief of Staff email pipeline.

Phases:
  1. Inbox & Triage  — pull threads, classify by priority
  2. Draft Generation — generate AI reply drafts
  3. Approval Gate   — review / approve / reject drafts
  4. Export Proof    — show approved drafts ready for sending
"""

import json
import os
from pathlib import Path

import streamlit as st

# ── Pipeline modules ──────────────────────────────────────────────────────────
from engine import fetch_threads, send_reply
from task_logger import log_action, get_action_log
from triage import triage_inbox
from context_builder import format_thread_history
from draft_machine import draft_reply, draft_reply_with_metadata

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="The Draft Desk",
    page_icon="",
    layout="wide",
)

# ── Red-Orange, White & Black theme styling ─────────────────────────────────
st.markdown(
    """
<style>
    /* ── Google Font Import ── */
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap');

    /* ── Color Variables ── */
    :root {
        --red-orange: #ff4500;
        --red-orange-light: #ff6a33;
        --red-orange-dark: #cc3700;
        --red-orange-glow: rgba(255, 69, 0, 0.4);
        --red-orange-subtle: rgba(255, 69, 0, 0.12);
        --white: #ffffff;
        --white-soft: #e0e0e0;
        --white-muted: #b0b0b0;
        --black: #000000;
        --black-light: #0d0d0d;
        --black-card: #111111;
        --black-surface: #1a1a1a;
        --border-subtle: rgba(255, 255, 255, 0.08);
    }

    /* ── Global Reset & Base ── */
    * {
        box-sizing: border-box;
    }

    .stApp {
        background: var(--black-light);
        color: var(--white-soft);
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    }

    .stApp header {
        background: rgba(0, 0, 0, 0.85);
        backdrop-filter: blur(12px);
        border-bottom: 1px solid var(--border-subtle);
    }

    /* ── Main title ── */
    .main-title {
        font-weight: 900;
        font-size: 2.4rem;
        color: var(--red-orange);
        margin-bottom: 4px;
        letter-spacing: -0.5px;
        text-shadow: 0 0 40px var(--red-orange-glow);
        animation: fadeInDown 0.8s ease-out;
    }

    @keyframes fadeInDown {
        from {
            opacity: 0;
            transform: translateY(-20px);
        }
        to {
            opacity: 1;
            transform: translateY(0);
        }
    }

    .sub-title {
        color: var(--white-muted);
        font-size: 1rem;
        margin-top: -8px;
        font-weight: 500;
        letter-spacing: 0.3px;
        animation: fadeIn 1s ease-out 0.3s both;
    }

    @keyframes fadeIn {
        from { opacity: 0; }
        to { opacity: 1; }
    }

    /* ── Sidebar Styling ── */
    .stApp [data-testid="stSidebar"] {
        background: var(--black);
        border-right: 1px solid var(--border-subtle);
    }

    .stApp [data-testid="stSidebar"] .stRadio label {
        color: var(--white-muted);
        font-weight: 500;
        padding: 8px 12px;
        border-radius: 10px;
        transition: all 0.3s ease;
    }

    .stApp [data-testid="stSidebar"] .stRadio label:hover {
        background: var(--red-orange-subtle);
        color: var(--red-orange);
        transform: translateX(4px);
    }

    .stApp [data-testid="stSidebar"] .stRadio div[data-testid="stMarkdownContainer"] {
        padding: 2px 0;
    }

    .stApp [data-testid="stSidebar"] .stButton button {
        color: var(--white-muted);
        border-radius: 12px;
        transition: all 0.3s ease;
        font-weight: 600;
    }

    .stApp [data-testid="stSidebar"] .stButton button:hover {
        transform: translateY(-2px);
        box-shadow: 0 8px 25px var(--red-orange-glow);
    }

    .sidebar-section-title {
        color: var(--red-orange);
        font-weight: 700;
        font-size: 0.8rem;
        text-transform: uppercase;
        letter-spacing: 1.2px;
        margin-bottom: 8px;
        padding-left: 4px;
    }

    .stSidebar hr {
        border-color: var(--border-subtle);
        margin: 16px 0;
    }

    /* ── Buttons ── */
    .stButton button {
        border-radius: 12px !important;
        font-weight: 700 !important;
        letter-spacing: 0.3px;
        transition: all 0.3s cubic-bezier(0.25, 0.46, 0.45, 0.94) !important;
        border: none !important;
        box-shadow: 0 4px 15px rgba(0, 0, 0, 0.3);
        animation: buttonSlideIn 0.5s ease-out;
    }

    @keyframes buttonSlideIn {
        from {
            opacity: 0;
            transform: translateY(10px);
        }
        to {
            opacity: 1;
            transform: translateY(0);
        }
    }

    .stButton button[kind="primary"] {
        background: var(--red-orange) !important;
        color: var(--white) !important;
        border: 1px solid var(--red-orange) !important;
    }

    .stButton button[kind="primary"]:hover {
        background: var(--red-orange-light) !important;
        transform: translateY(-3px) scale(1.02);
        box-shadow: 0 8px 30px var(--red-orange-glow);
        animation: pulse 0.6s ease-in-out;
    }

    @keyframes pulse {
        0%, 100% { transform: translateY(-3px) scale(1.02); }
        50% { transform: translateY(-4px) scale(1.04); }
    }

    .stButton button[kind="secondary"] {
        background: transparent !important;
        color: var(--white-soft) !important;
        border: 1px solid var(--border-subtle) !important;
    }

    .stButton button[kind="secondary"]:hover {
        border-color: var(--red-orange) !important;
        color: var(--red-orange) !important;
        transform: translateY(-2px);
    }

    /* ── Thread message boxes ── */
    .thread-message {
        background: var(--black-card);
        border: 1px solid var(--border-subtle);
        border-radius: 14px;
        padding: 14px 18px;
        margin-bottom: 12px;
        transition: all 0.3s ease;
        box-shadow: 0 4px 15px rgba(0, 0, 0, 0.3);
        animation: slideInLeft 0.5s ease-out;
    }

    .thread-message:hover {
        border-color: var(--red-orange);
        transform: translateY(-2px);
        box-shadow: 0 8px 25px rgba(0, 0, 0, 0.4);
    }

    @keyframes slideInLeft {
        from {
            opacity: 0;
            transform: translateX(-20px);
        }
        to {
            opacity: 1;
            transform: translateX(0);
        }
    }

    .msg-header {
        color: var(--red-orange);
        font-size: 0.85rem;
        margin-bottom: 6px;
        font-weight: 700;
        letter-spacing: 0.2px;
    }

    .msg-body {
        color: var(--white-soft);
        line-height: 1.6;
        font-size: 0.93rem;
        white-space: pre-wrap;
    }

    /* ── Priority Badges ── */
    .badge-urgent {
        display: inline-block;
        background: var(--red-orange);
        color: var(--white);
        padding: 4px 14px;
        border-radius: 20px;
        font-size: 0.7rem;
        font-weight: 800;
        text-transform: uppercase;
        letter-spacing: 0.8px;
        margin-right: 8px;
        box-shadow: 0 3px 10px var(--red-orange-glow);
        animation: pulse-badge 2s ease-in-out infinite;
    }

    .badge-needs-reply {
        display: inline-block;
        background: var(--black-surface);
        color: var(--red-orange);
        border: 1px solid var(--red-orange);
        padding: 4px 14px;
        border-radius: 20px;
        font-size: 0.7rem;
        font-weight: 800;
        text-transform: uppercase;
        letter-spacing: 0.8px;
        margin-right: 8px;
    }

    .badge-fyi {
        display: inline-block;
        background: var(--black-surface);
        color: var(--white-soft);
        border: 1px solid var(--border-subtle);
        padding: 4px 14px;
        border-radius: 20px;
        font-size: 0.7rem;
        font-weight: 800;
        text-transform: uppercase;
        letter-spacing: 0.8px;
        margin-right: 8px;
    }

    .badge-ignore {
        display: inline-block;
        background: transparent;
        color: var(--white-muted);
        border: 1px solid rgba(255, 255, 255, 0.1);
        padding: 4px 14px;
        border-radius: 20px;
        font-size: 0.7rem;
        font-weight: 800;
        text-transform: uppercase;
        letter-spacing: 0.8px;
        margin-right: 8px;
    }

    @keyframes pulse-badge {
        0%, 100% { transform: scale(1); }
        50% { transform: scale(1.05); }
    }

    /* ── Draft display box ── */
    .draft-box {
        background: var(--black-card);
        border: 1px solid var(--border-subtle);
        border-radius: 14px;
        padding: 18px 22px;
        margin-top: 8px;
        color: var(--white-soft);
        line-height: 1.7;
        font-size: 0.95rem;
        white-space: pre-wrap;
        box-shadow: 0 4px 20px rgba(0, 0, 0, 0.2);
        transition: all 0.3s ease;
        animation: slideInRight 0.5s ease-out;
    }

    .draft-box:hover {
        border-color: var(--red-orange);
        box-shadow: 0 8px 30px var(--red-orange-glow);
    }

    @keyframes slideInRight {
        from {
            opacity: 0;
            transform: translateX(20px);
        }
        to {
            opacity: 1;
            transform: translateX(0);
        }
    }

    /* ── Status indicators ── */
    .status-approved {
        background: var(--red-orange-subtle);
        border: 1px solid var(--red-orange);
        color: var(--red-orange);
        padding: 12px 18px;
        border-radius: 12px;
        font-weight: 700;
        text-align: center;
        margin-top: 12px;
        letter-spacing: 0.5px;
        box-shadow: 0 4px 15px var(--red-orange-glow);
    }

    .status-rejected {
        background: rgba(255, 255, 255, 0.04);
        border: 1px solid var(--border-subtle);
        color: var(--white-muted);
        padding: 12px 18px;
        border-radius: 12px;
        font-weight: 700;
        text-align: center;
        margin-top: 12px;
        letter-spacing: 0.5px;
    }

    /* ── Headings ── */
    h1, h2, h3 {
        font-family: 'Inter', sans-serif;
        color: var(--white);
        letter-spacing: -0.3px;
    }

    h1 {
        color: var(--red-orange);
        font-weight: 900;
        font-size: 2rem;
    }

    h2 {
        color: var(--white);
        font-weight: 800;
        border-bottom: 2px solid var(--border-subtle);
        padding-bottom: 8px;
    }

    h3 {
        margin-bottom: 16px;
        padding-bottom: 8px;
        border-bottom: 2px solid var(--border-subtle);
        font-weight: 700;
        font-size: 1.15rem;
    }

    /* ── Sidebar nav buttons ── */
    .nav-btn {
        width: 100%;
        text-align: left;
        padding: 10px 16px;
        margin-bottom: 4px;
        border-radius: 10px;
        border: none;
        background: transparent;
        color: var(--white-muted);
        font-size: 0.9rem;
        font-weight: 500;
        cursor: pointer;
        transition: all 0.3s ease;
    }
    .nav-btn:hover {
        background: var(--red-orange-subtle);
        color: var(--red-orange);
        transform: translateX(4px);
    }
    .nav-btn.active {
        background: var(--red-orange-subtle);
        color: var(--red-orange);
        font-weight: 700;
        border-left: 3px solid var(--red-orange);
    }

    /* ── Actionable count card ── */
    .actionable-card {
        background: var(--black-card);
        border: 1px solid var(--border-subtle);
        border-radius: 16px;
        padding: 20px 24px;
        text-align: center;
        margin-bottom: 20px;
        box-shadow: 0 4px 20px rgba(0, 0, 0, 0.3);
        transition: all 0.3s ease;
        animation: scaleIn 0.6s ease-out;
    }

    .actionable-card:hover {
        transform: translateY(-3px) scale(1.05);
        box-shadow: 0 8px 30px var(--red-orange-glow);
        border-color: var(--red-orange);
    }

    @keyframes scaleIn {
        from {
            opacity: 0;
            transform: scale(0.9);
        }
        to {
            opacity: 1;
            transform: scale(1);
        }
    }

    .actionable-count {
        font-size: 2.8rem;
        font-weight: 900;
        color: var(--red-orange);
        font-family: 'Inter', sans-serif;
    }

    .actionable-label {
        color: var(--white-muted);
        font-size: 0.85rem;
        font-weight: 500;
        letter-spacing: 0.3px;
    }

    /* ── Thread card in triage list ── */
    .thread-card {
        background: var(--black-card);
        border: 1px solid var(--border-subtle);
        border-radius: 14px;
        padding: 16px 20px;
        margin-bottom: 10px;
        cursor: pointer;
        transition: all 0.3s ease;
        box-shadow: 0 4px 15px rgba(0, 0, 0, 0.2);
        animation: fadeInUp 0.5s ease-out;
    }
    .thread-card:hover {
        border-color: var(--red-orange);
        transform: translateY(-3px);
        box-shadow: 0 8px 25px var(--red-orange-glow);
    }

    @keyframes fadeInUp {
        from {
            opacity: 0;
            transform: translateY(20px);
        }
        to {
            opacity: 1;
            transform: translateY(0);
        }
    }
    .thread-card .subject {
        color: var(--white);
        font-weight: 700;
        font-size: 1rem;
        margin-bottom: 4px;
        font-family: 'Inter', sans-serif;
    }
    .thread-card .meta {
        color: var(--white-muted);
        font-size: 0.82rem;
    }
    .thread-card .snippet {
        color: var(--white-muted);
        font-size: 0.88rem;
        margin-top: 6px;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
    }

    /* ── Text area styling ── */
    .stTextArea textarea {
        background: var(--black-card) !important;
        color: var(--white-soft) !important;
        border: 1px solid var(--border-subtle) !important;
        border-radius: 12px !important;
        transition: all 0.3s ease !important;
        font-family: 'Inter', monospace !important;
        font-size: 0.9rem !important;
    }

    .stTextArea textarea:focus {
        border-color: var(--red-orange) !important;
        box-shadow: 0 0 20px var(--red-orange-glow) !important;
    }

    /* ── Streamlit custom overrides ── */
    .stAlert {
        border-radius: 12px !important;
        border: none !important;
    }

    .stAlert [data-testid="stMarkdownContainer"] {
        font-weight: 500;
    }

    .stAlert[data-baseweb="notification"] {
        border-radius: 12px !important;
    }

    /* Success alerts */
    .stAlert[data-baseweb="notification"][kind="positive"] {
        background: var(--red-orange-subtle) !important;
        border: 1px solid var(--red-orange) !important;
        color: var(--red-orange) !important;
    }

    /* Error alerts */
    .stAlert[data-baseweb="notification"][kind="error"] {
        background: rgba(255, 69, 0, 0.08) !important;
        border: 1px solid var(--red-orange) !important;
        color: var(--red-orange-light) !important;
    }

    /* Info alerts */
    .stAlert[data-baseweb="notification"][kind="info"] {
        background: rgba(255, 255, 255, 0.04) !important;
        border: 1px solid var(--border-subtle) !important;
        color: var(--white-soft) !important;
    }

    /* Warning alerts */
    .stAlert[data-baseweb="notification"][kind="warning"] {
        background: var(--red-orange-subtle) !important;
        border: 1px solid var(--red-orange) !important;
        color: var(--red-orange) !important;
    }

    /* ── Expander styling ── */
    .streamlit-expanderHeader {
        background: var(--black-card) !important;
        border-radius: 12px !important;
        border: 1px solid var(--border-subtle) !important;
        font-weight: 600 !important;
        color: var(--white-soft) !important;
        transition: all 0.3s ease !important;
    }

    .streamlit-expanderHeader:hover {
        background: var(--black-surface) !important;
        border-color: var(--red-orange) !important;
    }

    .streamlit-expanderContent {
        border: 1px solid var(--border-subtle) !important;
        border-top: none !important;
        border-radius: 0 0 12px 12px !important;
        padding: 12px 16px !important;
        background: rgba(0, 0, 0, 0.3) !important;
    }

    /* ── Progress bar ── */
    .stProgress > div > div > div > div {
        background: var(--red-orange) !important;
        border-radius: 10px !important;
    }

    .stProgress > div > div {
        background: var(--border-subtle) !important;
        border-radius: 10px !important;
    }

    /* ── Status message (for pipeline) ── */
    .stStatusWidget {
        border-radius: 16px !important;
        background: var(--black-card) !important;
        border: 1px solid var(--border-subtle) !important;
        box-shadow: 0 4px 20px rgba(0, 0, 0, 0.3) !important;
    }

    /* ── Select box ── */
    .stSelectbox div[data-baseweb="select"] > div {
        background: var(--black-card) !important;
        border: 1px solid var(--border-subtle) !important;
        border-radius: 12px !important;
        color: var(--white-soft) !important;
    }

    .stSelectbox ul {
        background: var(--black) !important;
        border: 1px solid var(--border-subtle) !important;
        border-radius: 12px !important;
    }

    .stSelectbox li {
        color: var(--white-soft) !important;
    }

    .stSelectbox li:hover {
        background: var(--red-orange-subtle) !important;
        color: var(--red-orange) !important;
    }

    /* ── Number input ── */
    .stNumberInput input {
        background: var(--black-card) !important;
        border: 1px solid var(--border-subtle) !important;
        border-radius: 12px !important;
        color: var(--white-soft) !important;
    }

    .stNumberInput input:focus {
        border-color: var(--red-orange) !important;
        box-shadow: 0 0 20px var(--red-orange-glow) !important;
    }

    /* ── Tabs ── */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
        background: var(--black);
        border-radius: 12px;
        padding: 4px;
    }

    .stTabs [data-baseweb="tab"] {
        border-radius: 10px !important;
        font-weight: 600 !important;
        color: var(--white-muted) !important;
        transition: all 0.3s ease !important;
    }

    .stTabs [data-baseweb="tab"]:hover {
        color: var(--white) !important;
        background: rgba(255, 255, 255, 0.04) !important;
    }

    .stTabs [data-baseweb="tab"][aria-selected="true"] {
        background: var(--red-orange-subtle) !important;
        color: var(--red-orange) !important;
    }

    /* ── Dataframe / table styling ── */
    .stDataFrame {
        border-radius: 12px !important;
        overflow: hidden;
    }

    /* ── Spinner ── */
    .stSpinner {
        color: var(--red-orange) !important;
    }

    .stSpinner > div {
        border-color: var(--red-orange) transparent transparent transparent !important;
    }

    /* ── Links ── */
    a {
        color: var(--red-orange) !important;
        text-decoration: none !important;
        font-weight: 700 !important;
        transition: all 0.3s ease !important;
    }

    a:hover {
        color: var(--red-orange-light) !important;
        text-decoration: underline !important;
    }

    /* ── Custom scrollbar ── */
    ::-webkit-scrollbar {
        width: 8px;
        height: 8px;
    }

    ::-webkit-scrollbar-track {
        background: var(--black);
        border-radius: 10px;
    }

    ::-webkit-scrollbar-thumb {
        background: var(--red-orange);
        border-radius: 10px;
        transition: all 0.3s ease;
    }

    ::-webkit-scrollbar-thumb:hover {
        background: var(--red-orange-light);
    }

    /* ── Horizontal rule ── */
    hr {
        background: var(--border-subtle) !important;
        height: 1px !important;
        border: none !important;
        margin: 24px 0 !important;
    }

    /* ── Checkbox ── */
    .stCheckbox label {
        color: var(--white-soft) !important;
    }

    /* ── Columns equal spacing ── */
    [data-testid="column"] {
        padding: 0 6px;
    }

    /* ── Multi-line caption / small text ── */
    .stCaption {
        color: var(--white-muted) !important;
        font-size: 0.8rem !important;
    }
</style>
""",
    unsafe_allow_html=True,
)

# ── Helpers ───────────────────────────────────────────────────────────────────

SAMPLE_THREADS_PATH = Path("sample_threads.json")


def _get_calendar_engine():
    """Import calendar_engine module."""
    import calendar_engine
    return calendar_engine


def generate_proof_markdown(export_data: list[dict]) -> str:
    """Generate a Markdown proof-of-work document for approved drafts."""
    from datetime import date
    lines = []
    lines.append("# The Draft Desk — Proof of Work")
    lines.append("")
    lines.append(f"**Date:** {date.today().strftime('%B %d, %Y')}")
    lines.append("")
    lines.append("---")
    lines.append("")
    for item in export_data:
        lines.append(f"## {item['subject']}")
        lines.append("")
        lines.append(f"**Replying to:** {item['replying_to']}")
        lines.append("")
        lines.append("### Original Thread")
        lines.append("")
        for msg in item.get("messages", []):
            lines.append(f"> **{msg['from']}** &middot; {msg['date']}")
            lines.append(">")
            for line in msg["body"].split("\n"):
                lines.append(f"> {line}")
            lines.append("")
        lines.append("### Approved Draft")
        lines.append("")
        lines.append("```")
        lines.append(item["draft"])
        lines.append("```")
        lines.append("")
        lines.append("---")
        lines.append("")
    return "\n".join(lines)


def generate_proof_html(export_data: list[dict]) -> str:
    """Generate a styled HTML proof-of-work document for approved drafts."""
    from datetime import date
    today_str = date.today().strftime("%B %d, %Y")

    # Build thread cards HTML
    cards_html = ""
    for item in export_data:
        # Original thread messages
        thread_msgs = ""
        for msg in item.get("messages", []):
            thread_msgs += f"""
            <div class="thread-msg">
                <div class="msg-header"><strong>{msg['from']}</strong> &middot; {msg['date']}</div>
                <div class="msg-body">{msg['body'].replace(chr(10), '<br>')}</div>
            </div>"""

        cards_html += f"""
        <div class="proof-card">
            <h2>{item['subject']}</h2>
            <p class="replying-to"><strong>Replying to:</strong> {item['replying_to']}</p>
            <div class="grid-2col">
                <div class="grid-left">
                    <h3>Original Thread</h3>
                    {thread_msgs}
                </div>
                <div class="grid-right">
                    <h3>Approved Draft</h3>
                    <div class="draft-content">{item['draft'].replace(chr(10), '<br>')}</div>
                </div>
            </div>
        </div>"""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>The Draft Desk — Proof of Work</title>
<style>
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    body {{
        background: linear-gradient(135deg, #0f0c29 0%, #1a1a3e 50%, #2d1b4e 100%);
        color: #e0e0e0;
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
        padding: 40px 20px;
        line-height: 1.6;
        min-height: 100vh;
    }}
    .container {{
        max-width: 1200px;
        margin: 0 auto;
    }}
    header {{
        text-align: center;
        margin-bottom: 40px;
        padding-bottom: 20px;
        border-bottom: 2px solid rgba(255, 255, 255, 0.08);
    }}
    header h1 {{
        font-size: 2rem;
        background: linear-gradient(135deg, #f093fb 0%, #f5576c 50%, #4facfe 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
        margin-bottom: 8px;
        font-family: 'Segoe UI', 'Fredoka', sans-serif;
        font-weight: 700;
    }}
    header .date {{
        color: #a89bc0;
        font-size: 0.95rem;
    }}
    .proof-card {{
        background: linear-gradient(135deg, rgba(30, 30, 60, 0.9) 0%, rgba(40, 25, 65, 0.9) 100%);
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 16px;
        padding: 24px;
        margin-bottom: 32px;
        box-shadow: 0 4px 20px rgba(0, 0, 0, 0.2);
        transition: transform 0.3s ease, box-shadow 0.3s ease;
    }}
    .proof-card:hover {{
        transform: translateY(-2px);
        box-shadow: 0 8px 30px rgba(240, 147, 251, 0.1);
    }}
    .proof-card h2 {{
        color: #e0e0e0;
        font-size: 1.3rem;
        margin-bottom: 6px;
    }}
    .replying-to {{
        color: #a89bc0;
        font-size: 0.9rem;
        margin-bottom: 16px;
    }}
    .grid-2col {{
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 20px;
    }}
    @media (max-width: 768px) {{
        .grid-2col {{ grid-template-columns: 1fr; }}
    }}
    .grid-left h3,
    .grid-right h3 {{
        font-size: 0.95rem;
        margin-bottom: 12px;
        padding-bottom: 6px;
        border-bottom: 1px solid rgba(255, 255, 255, 0.08);
    }}
    .grid-left h3 {{
        background: linear-gradient(135deg, #f5a623, #f093fb);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
    }}
    .grid-right h3 {{
        background: linear-gradient(135deg, #2d6a4f, #43e97b);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
    }}
    .grid-left {{
        border: 1px solid rgba(245, 166, 35, 0.3);
        border-radius: 12px;
        padding: 16px;
        background: rgba(15, 12, 41, 0.6);
    }}
    .grid-right {{
        border: 1px solid rgba(67, 233, 123, 0.3);
        border-radius: 12px;
        padding: 16px;
        background: rgba(15, 12, 41, 0.6);
    }}
    .thread-msg {{
        background: linear-gradient(135deg, rgba(30, 30, 60, 0.6) 0%, rgba(40, 25, 65, 0.6) 100%);
        border: 1px solid rgba(255, 255, 255, 0.06);
        border-radius: 10px;
        padding: 10px 14px;
        margin-bottom: 10px;
        transition: border-color 0.3s ease;
    }}
    .thread-msg:hover {{
        border-color: rgba(79, 172, 254, 0.3);
    }}
    .msg-header {{
        color: #f5576c;
        font-size: 0.85rem;
        margin-bottom: 4px;
        font-weight: 600;
    }}
    .msg-body {{
        color: #d0c8e0;
        font-size: 0.9rem;
        white-space: pre-wrap;
    }}
    .draft-content {{
        background: linear-gradient(135deg, rgba(30, 30, 60, 0.6) 0%, rgba(40, 25, 65, 0.6) 100%);
        border: 1px solid rgba(67, 233, 123, 0.2);
        border-radius: 10px;
        padding: 14px;
        color: #e0e0e0;
        font-size: 0.95rem;
        white-space: pre-wrap;
        line-height: 1.6;
    }}
    footer {{
        text-align: center;
        color: #555;
        font-size: 0.8rem;
        margin-top: 40px;
        padding-top: 20px;
        border-top: 1px solid rgba(255, 255, 255, 0.06);
    }}
</style>
</head>
<body>
<div class="container">
    <header>
        <h1>The Draft Desk — Proof of Work</h1>
        <p class="date">{today_str}</p>
    </header>
    {cards_html}
    <footer>
        <p>Generated by The Draft Desk &middot; AI Chief of Staff</p>
    </footer>
</div>
</body>
</html>"""
    return html


def _load_sample_threads() -> list[dict]:
    """Load sample threads from the JSON fallback file."""
    if SAMPLE_THREADS_PATH.exists():
        with open(SAMPLE_THREADS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def _convert_engine_thread(engine_thread: dict) -> dict:
    """Convert an engine.py thread dict into the pipeline format.

    engine.py returns:  {thread_id, message_id, sender, subject, snippet,
                         date, references, in_reply_to, msg_id_header}
    pipeline expects:   {id, subject, messages: [{from, date, body}],
                         thread_id, message_id, references, in_reply_to,
                         msg_id_header}
    """
    return {
        "id": engine_thread["thread_id"],
        "subject": engine_thread["subject"],
        "messages": [
            {
                "from": engine_thread["sender"],
                "date": engine_thread["date"],
                "body": engine_thread["snippet"],
            }
        ],
        # Gmail metadata for send_reply()
        "thread_id": engine_thread.get("thread_id", ""),
        "message_id": engine_thread.get("message_id", ""),
        "references": engine_thread.get("references", ""),
        "in_reply_to": engine_thread.get("in_reply_to", ""),
        "msg_id_header": engine_thread.get("msg_id_header", ""),
    }


def triage_threads(threads: list[dict]) -> list[dict]:
    """Triage threads using the triage_inbox function.

    Converts pipeline thread format to triage input format and returns
    triaged threads with priority/category/reason.
    """
    triage_input = []
    for t in threads:
        first_msg = t["messages"][0] if t["messages"] else {}
        triage_input.append({
            "sender": first_msg.get("from", ""),
            "subject": t.get("subject", ""),
            "snippet": first_msg.get("body", ""),
        })

    return triage_inbox(triage_input)


def _get_draft_reply(pipeline_thread: dict) -> str:
    """Wrapper around draft_reply for consistent error handling."""
    return draft_reply(pipeline_thread)


def run_full_pipeline() -> list[str]:
    """Run the full email pipeline: fetch, triage, draft, and prepare for approval.

    Returns a list of log strings describing the pipeline progress.
    """
    log = []

    # Step 1: Fetch threads based on source
    try:
        source = st.session_state.source
        if source == "Gmail (via engine.py)":
            raw_threads = fetch_threads(
                max_results=st.session_state.max_threads)
            st.session_state.threads = [
                _convert_engine_thread(t) for t in raw_threads
            ]
            log.append(
                f"Fetched {len(st.session_state.threads)} threads from Gmail.")
        else:
            st.session_state.threads = _load_sample_threads()
            log.append(
                f"Fetched {len(st.session_state.threads)} sample threads.")
    except Exception as e:
        log.append(f"Error fetching threads: {e}")
        return log

    if not st.session_state.threads:
        log.append("No threads found. Pipeline stopped.")
        return log

    # Step 2: Triage threads
    try:
        st.session_state.triaged = triage_threads(st.session_state.threads)
        urgent_count = sum(
            1 for t in st.session_state.triaged if t.get("priority") == "urgent")
        needs_reply_count = sum(
            1 for t in st.session_state.triaged if t.get("priority") == "needs-reply")
        log.append(f"Triaged: {urgent_count} urgent, {needs_reply_count} needs-reply, "
                   f"{len(st.session_state.triaged) - urgent_count - needs_reply_count} other.")
    except Exception as e:
        log.append(f"Error during triage: {e}")
        return log

    # Step 3: Reset downstream session state
    st.session_state.drafts = {}
    st.session_state.approved = {}
    st.session_state.rejected = set()
    st.session_state.sent = set()
    st.session_state.booked = {}
    log.append(
        "Reset downstream state (drafts, approved, rejected, sent, booked).")

    # Step 4: Generate drafts for urgent + needs-reply threads
    actionable = [
        t for t in st.session_state.triaged
        if t.get("priority") in ("urgent", "needs-reply")
    ]

    if not actionable:
        log.append("No actionable threads found. Pipeline complete.")
        st.session_state.current_phase = "Approval Gate"
        return log

    # Resolve pipeline threads for each actionable triage result
    actionable_pairs = []
    for t in actionable:
        pt = None
        for p in st.session_state.threads:
            if p.get("subject") == t.get("subject"):
                pt = p
                break
        actionable_pairs.append((t, pt))

    drafts_generated = 0
    drafts_failed = 0

    for idx, (triage_t, pipeline_t) in enumerate(actionable_pairs):
        thread_key = triage_t.get("subject", f"thread_{idx}")

        if pipeline_t is None:
            log.append(
                f"Draft {idx + 1}/{len(actionable_pairs)}: {thread_key} - skipped (thread data not available).")
            drafts_failed += 1
            continue

        try:
            draft_text = _get_draft_reply(pipeline_t)
            st.session_state.drafts[thread_key] = draft_text
            drafts_generated += 1
            log.append(
                f"Draft {idx + 1}/{len(actionable_pairs)}: {thread_key[:40]}... - done.")
        except Exception as e:
            drafts_failed += 1
            log.append(
                f"Draft {idx + 1}/{len(actionable_pairs)}: {thread_key[:40]}... - failed: {e}")

    # Step 5: Set current phase
    st.session_state.current_phase = "Approval Gate"

    # Final summary
    log.append(
        f"Pipeline complete! {drafts_generated} drafts ready for review.")
    if drafts_failed > 0:
        log.append(f"Note: {drafts_failed} draft(s) failed to generate.")

    return log


def _render_pipeline_execution():
    """Execute the full pipeline with live progress UI.

    Runs the same logic as run_full_pipeline() but inline to update UI at each step.
    Uses st.status for live progress display with checkmarks/X for each step.
    """
    pipeline_log = []

    with st.status("Running full pipeline...", expanded=True) as status:
        # Step 1: Fetch threads
        status.update(label="Fetching threads...")
        try:
            source = st.session_state.source
            if source == "Gmail (via engine.py)":
                raw_threads = fetch_threads(
                    max_results=st.session_state.max_threads)
                st.session_state.threads = [
                    _convert_engine_thread(t) for t in raw_threads
                ]
                pipeline_log.append(
                    f"Fetched {len(st.session_state.threads)} threads from Gmail.")
            else:
                st.session_state.threads = _load_sample_threads()
                pipeline_log.append(
                    f"Fetched {len(st.session_state.threads)} sample threads.")

            st.write("Fetch complete")
        except Exception as e:
            pipeline_log.append(f"Error fetching threads: {e}")
            st.write("Fetch failed")
            status.update(label="Pipeline failed", state="error")
            st.session_state.pipeline_running = False
            return

        if not st.session_state.threads:
            pipeline_log.append("No threads found. Pipeline stopped.")
            st.write("No threads found")
            status.update(label="Pipeline stopped", state="error")
            st.session_state.pipeline_running = False
            return

        # Step 2: Triage threads
        status.update(label="Triaging threads...")
        try:
            st.session_state.triaged = triage_threads(st.session_state.threads)
            urgent_count = sum(
                1 for t in st.session_state.triaged if t.get("priority") == "urgent")
            needs_reply_count = sum(
                1 for t in st.session_state.triaged if t.get("priority") == "needs-reply")
            pipeline_log.append(f"Triaged: {urgent_count} urgent, {needs_reply_count} needs-reply, "
                                f"{len(st.session_state.triaged) - urgent_count - needs_reply_count} other.")
            st.write("Triage complete")
        except Exception as e:
            pipeline_log.append(f"Error during triage: {e}")
            st.write("Triage failed")
            status.update(label="Pipeline failed", state="error")
            st.session_state.pipeline_running = False
            return

        # Step 3: Reset downstream session state
        st.session_state.drafts = {}
        st.session_state.approved = {}
        st.session_state.rejected = set()
        st.session_state.sent = set()
        st.session_state.booked = {}
        pipeline_log.append(
            "Reset downstream state (drafts, approved, rejected, sent, booked).")

        # Step 4: Generate drafts for urgent + needs-reply threads
        actionable = [
            t for t in st.session_state.triaged
            if t.get("priority") in ("urgent", "needs-reply")
        ]

        if not actionable:
            pipeline_log.append(
                "No actionable threads found. Pipeline complete.")
            st.write("No actionable threads to draft")
            status.update(label="Pipeline complete", state="complete")
            st.session_state.pipeline_running = False
            st.session_state.current_phase = "Approval Gate"
            st.session_state.pipeline_log = pipeline_log
            st.rerun()
            return

        # Resolve pipeline threads for each actionable triage result
        actionable_pairs = []
        for t in actionable:
            pt = None
            for p in st.session_state.threads:
                if p.get("subject") == t.get("subject"):
                    pt = p
                    break
            actionable_pairs.append((t, pt))

        # Draft loop with progress updates
        drafts_generated = 0
        drafts_failed = 0
        total_drafts = len(actionable_pairs)

        for idx, (triage_t, pipeline_t) in enumerate(actionable_pairs):
            thread_key = triage_t.get("subject", f"thread_{idx}")
            status.update(
                label=f"Drafting {idx + 1}/{total_drafts}: {thread_key[:40]}...")

            if pipeline_t is None:
                pipeline_log.append(
                    f"Draft {idx + 1}/{total_drafts}: {thread_key} - skipped (thread data not available).")
                st.write(
                    f"Draft {idx + 1}/{total_drafts}: {thread_key[:40]}... - skipped")
                drafts_failed += 1
                continue

            try:
                draft_text = _get_draft_reply(pipeline_t)
                st.session_state.drafts[thread_key] = draft_text
                drafts_generated += 1
                pipeline_log.append(
                    f"Draft {idx + 1}/{total_drafts}: {thread_key[:40]}... - done.")
                st.write(
                    f"Draft {idx + 1}/{total_drafts}: {thread_key[:40]}... - done")
            except Exception as e:
                drafts_failed += 1
                pipeline_log.append(
                    f"Draft {idx + 1}/{total_drafts}: {thread_key[:40]}... - failed: {e}")
                st.write(
                    f"Draft {idx + 1}/{total_drafts}: {thread_key[:40]}... - failed")

        # Final summary
        pipeline_log.append(
            f"Pipeline complete! {drafts_generated} drafts ready for review.")
        if drafts_failed > 0:
            pipeline_log.append(
                f"Note: {drafts_failed} draft(s) failed to generate.")

        status.update(label="Pipeline complete", state="complete")

    # Outside status block: finalize session state
    st.session_state.pipeline_log = pipeline_log
    st.session_state.current_phase = "Approval Gate"
    st.session_state.pipeline_running = False
    st.rerun()


def _priority_badge_html(priority: str) -> str:
    """Return an HTML span for a priority badge."""
    css_class = f"badge-{priority}" if priority in (
        "urgent", "needs-reply", "fyi", "ignore") else "badge-ignore"
    return f'<span class="{css_class}">{priority}</span>'


def _render_thread_detail(thread: dict) -> str:
    """Render a thread's messages as HTML."""
    parts = [f"<h3>{thread.get('subject', '(no subject)')}</h3>"]
    for msg in thread.get("messages", []):
        parts.append(
            f'<div class="thread-message">'
            f'<div class="msg-header"><strong>{msg["from"]}</strong> &middot; {msg["date"]}</div>'
            f'<div class="msg-body">{msg["body"].replace(chr(10), "<br>")}</div>'
            f"</div>"
        )
    return "\n".join(parts)


# ── Session state initialisation ─────────────────────────────────────────────

if "threads" not in st.session_state:
    st.session_state.threads = []          # raw threads (pipeline format)
if "triaged" not in st.session_state:
    st.session_state.triaged = []          # triaged threads with priority
if "drafts" not in st.session_state:
    st.session_state.drafts = {}           # {thread_id: draft_text}
if "approved" not in st.session_state:
    st.session_state.approved = {}         # {thread_id: draft_text}
if "rejected" not in st.session_state:
    st.session_state.rejected = set()      # set of thread_ids
if "current_phase" not in st.session_state:
    st.session_state.current_phase = "Inbox & Triage"
if "source" not in st.session_state:
    st.session_state.source = "Sample threads for demo"
if "expanded_thread" not in st.session_state:
    st.session_state.expanded_thread = None
if "generating_for" not in st.session_state:
    st.session_state.generating_for = None
if "draft_result" not in st.session_state:
    st.session_state.draft_result = None
if "edit_text" not in st.session_state:
    st.session_state.edit_text = ""
if "sent" not in st.session_state:
    st.session_state.sent = set()           # set of thread_keys that have been sent
if "booked" not in st.session_state:
    st.session_state.booked = {}           # {thread_key: event_dict with htmlLink}
if "pipeline_running" not in st.session_state:
    st.session_state.pipeline_running = False  # whether full pipeline is executing
if "pipeline_log" not in st.session_state:
    st.session_state.pipeline_log = []      # log messages from pipeline execution


# ── Sidebar ───────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown(
        '<div class="main-title" style="font-size: 1.6rem;">The Draft Desk</div>',
        unsafe_allow_html=True,
    )
    st.markdown("---")

    # Run Full Pipeline button
    if st.button(
        "Run Full Pipeline",
        type="primary",
        use_container_width=True,
        key="run_pipeline_button",
    ):
        st.session_state.pipeline_running = True
        st.rerun()
    st.caption("Fetches, triages, and drafts — stops at Approval Gate.")
    st.markdown("---")

    # Source selector
    st.markdown(
        '<div class="sidebar-section-title">Email Source</div>',
        unsafe_allow_html=True,
    )
    source = st.radio(
        "Choose source:",
        ["Gmail (via engine.py)", "Sample threads for demo"],
        key="source_radio",
        label_visibility="collapsed",
    )
    st.session_state.source = source
    st.markdown("---")

    # Thread count setting
    st.markdown(
        '<div class="sidebar-section-title">Threads to Pull</div>',
        unsafe_allow_html=True,
    )
    max_threads = st.number_input(
        "Number of threads to fetch & triage:",
        min_value=1,
        max_value=50,
        value=st.session_state.get("max_threads", 5),
        step=1,
        key="max_threads_input",
        label_visibility="collapsed",
    )
    st.session_state.max_threads = max_threads
    st.markdown("---")

    # Workflow navigation
    st.markdown(
        '<div class="sidebar-section-title">Workflow</div>',
        unsafe_allow_html=True,
    )
    phases = ["Inbox & Triage", "Draft Generation",
              "Approval Gate", "Export Proof"]
    for phase in phases:
        active = phase == st.session_state.current_phase
        btn_class = "nav-btn active" if active else "nav-btn"
        if st.button(
            phase,
            key=f"nav_{phase}",
            use_container_width=True,
            type="secondary" if not active else "primary",
        ):
            st.session_state.current_phase = phase
            st.rerun()

    st.markdown("---")
    st.caption("AI Chief of Staff · v1.0")


# ── Main content area ─────────────────────────────────────────────────────────

st.markdown(
    '<div class="main-title">The Draft Desk</div>',
    unsafe_allow_html=True,
)
st.markdown(
    '<div class="sub-title">Your AI Chief of Staff — triage, draft, approve, and export.</div>',
    unsafe_allow_html=True,
)
st.markdown("---")

# ── Pipeline execution routing ─────────────────────────────────────────────────

if st.session_state.pipeline_running:
    _render_pipeline_execution()

# ── PHASE 1: Inbox & Triage ──────────────────────────────────────────────────

elif st.session_state.current_phase == "Inbox & Triage":

    st.header("Inbox & Triage")

    # Pull & Triage button
    col1, col2 = st.columns([2, 3])
    with col1:
        pull_clicked = st.button(
            "Pull & Triage Threads",
            type="primary",
            use_container_width=True,
        )

    if pull_clicked:
        try:
            if st.session_state.source == "Gmail (via engine.py)":
                # Real Gmail fetch
                with st.spinner("Fetching inbox threads from Gmail..."):
                    raw_threads = fetch_threads(
                        max_results=st.session_state.max_threads)
                    # Convert engine format → pipeline format
                    st.session_state.threads = [
                        _convert_engine_thread(t) for t in raw_threads
                    ]
            else:
                st.session_state.threads = _load_sample_threads()

            if not st.session_state.threads:
                st.warning("No threads found.")
            else:
                # Convert pipeline format → triage format
                triage_input = []
                for t in st.session_state.threads:
                    first_msg = t["messages"][0] if t["messages"] else {}
                    triage_input.append({
                        "sender": first_msg.get("from", ""),
                        "subject": t.get("subject", ""),
                        "snippet": first_msg.get("body", ""),
                    })

                # Run triage with a progress bar
                total_threads = len(triage_input)
                estimated_seconds = total_threads * 4.5  # ~4s API delay + response time
                triage_progress = st.progress(
                    0,
                    text=f"Triaging {total_threads} threads "
                    f"(~{estimated_seconds:.0f}s due to API rate limits)…",
                )

                def _update_progress(current, total, subject):
                    pct = current / total
                    triage_progress.progress(
                        pct,
                        text=f"Triaging ({current}/{total}): {subject[:50]}…",
                    )

                st.session_state.triaged = triage_inbox(
                    triage_input, progress_callback=_update_progress
                )

                # Clear the progress bar
                triage_progress.empty()

                st.success(
                    f"Triaged {len(st.session_state.triaged)} threads. "
                    f"See results below."
                )
        except Exception as e:
            st.error(f"Failed to pull threads: {e}")
            st.session_state.threads = []
            st.session_state.triaged = []

    # Display triaged threads
    if st.session_state.triaged:
        # Count actionable (urgent + needs-reply)
        actionable = [
            t for t in st.session_state.triaged
            if t.get("priority") in ("urgent", "needs-reply")
        ]

        # Actionable count card
        st.markdown(
            f'<div class="actionable-card">'
            f'<div class="actionable-count">{len(actionable)}</div>'
            f'<div class="actionable-label">actionable threads (urgent + needs-reply)</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

        # Group by priority
        priority_order = ["urgent", "needs-reply", "fyi", "ignore"]
        priority_labels = {
            "urgent": "Urgent",
            "needs-reply": "Needs Reply",
            "fyi": "FYI",
            "ignore": "Ignore",
        }

        for priority in priority_order:
            group = [
                t for t in st.session_state.triaged
                if t.get("priority") == priority
            ]
            if not group:
                continue

            st.subheader(priority_labels.get(priority, priority.title()))
            st.markdown(
                f'<p style="color: var(--white-muted); margin-top: -8px; font-size: 0.85rem;">{len(group)} thread{"s" if len(group) != 1 else ""}</p>', unsafe_allow_html=True)

            for i, thread in enumerate(group):
                # Find the matching pipeline thread for display
                pipeline_thread = None
                for pt in st.session_state.threads:
                    if pt.get("subject") == thread.get("subject"):
                        pipeline_thread = pt
                        break

                subject = thread.get("subject", "(no subject)")
                sender = thread.get("sender", "unknown")
                reason = thread.get("reason", "")
                snippet = thread.get("snippet", "")

                # Use expander for each thread
                with st.expander(f"{subject} — *{sender}*", expanded=False):
                    st.markdown(
                        f'<p style="color: var(--red-orange); font-size: 0.9rem;">'
                        f'{_priority_badge_html(thread.get("priority", "unknown"))} '
                        f'<strong>Category:</strong> {thread.get("category", "other")} &nbsp;|&nbsp; '
                        f'<strong>Reason:</strong> {reason}'
                        f'</p>',
                        unsafe_allow_html=True,
                    )

                    if pipeline_thread:
                        st.markdown(
                            _render_thread_detail(pipeline_thread),
                            unsafe_allow_html=True,
                        )
                    else:
                        st.markdown(
                            f'<div class="thread-message">'
                            f'<div class="msg-header"><strong>{sender}</strong></div>'
                            f'<div class="msg-body">{snippet}</div>'
                            f'</div>',
                            unsafe_allow_html=True,
                        )

            st.markdown("---")

    elif not pull_clicked:
        st.info(
            "Select a source from the sidebar and click "
            "**Pull & Triage Threads** to get started."
        )


# ── PHASE 2: Draft Generation ────────────────────────────────────────────────

elif st.session_state.current_phase == "Draft Generation":

    st.header("Draft Generation")

    if not st.session_state.triaged:
        st.warning(
            "No triaged threads available. Go to **Inbox & Triage** first.")
    else:
        # Get only actionable threads (urgent + needs-reply)
        actionable = [
            t for t in st.session_state.triaged
            if t.get("priority") in ("urgent", "needs-reply")
        ]

        if not actionable:
            st.info("No actionable threads (urgent / needs-reply) to draft for.")
        else:
            # Resolve pipeline threads for each actionable triage result
            actionable_pairs = []  # (triage_thread, pipeline_thread)
            for t in actionable:
                pt = None
                for p in st.session_state.threads:
                    if p.get("subject") == t.get("subject"):
                        pt = p
                        break
                actionable_pairs.append((t, pt))

            st.markdown(
                f"<p style='color: var(--white-muted);'>"
                f"{len(actionable_pairs)} actionable thread{'s' if len(actionable_pairs) != 1 else ''} — "
                f"generate drafts all at once or individually below.</p>",
                unsafe_allow_html=True,
            )

            # ── "Generate All Drafts" button with progress bar ──────────────
            if st.button(
                "Generate All Drafts",
                type="primary",
                use_container_width=True,
                key="generate_all",
            ):
                # Clear existing drafts for these threads and regenerate
                progress_bar = st.progress(0, text="Initialising...")
                total = len(actionable_pairs)
                errors = 0

                for idx, (triage_t, pipeline_t) in enumerate(actionable_pairs):
                    thread_key = triage_t.get("subject", f"thread_{idx}")
                    progress_bar.progress(
                        (idx) / total,
                        text=f"Generating draft {idx + 1} of {total}: {thread_key[:50]}…",
                    )

                    if pipeline_t is None:
                        st.warning(
                            f"Skipping '{thread_key}' — thread data not available."
                        )
                        errors += 1
                        continue

                    try:
                        draft_text = draft_reply(pipeline_t)
                        st.session_state.drafts[thread_key] = draft_text
                    except Exception as e:
                        st.error(
                            f"Failed to generate draft for '{thread_key}': {e}"
                        )
                        errors += 1

                progress_bar.progress(
                    1.0,
                    text=f"Done — {total - errors} of {total} draft{'s' if total - errors != 1 else ''} generated."
                    if errors == 0
                    else f"Completed with {errors} error{'s' if errors != 1 else ''}.",
                )

                if errors == 0:
                    st.success(
                        "All drafts generated! Head over to **Approval Gate** "
                        "to review, edit, and approve."
                    )

            st.markdown("---")

            # ── Individual thread + draft cards ─────────────────────────────
            for idx, (triage_t, pipeline_t) in enumerate(actionable_pairs):
                subject = triage_t.get("subject", "(no subject)")
                sender = triage_t.get("sender", "unknown")
                reason = triage_t.get("reason", "")
                thread_key = subject

                draft_text = st.session_state.drafts.get(thread_key, "")

                with st.expander(
                    f"{'Done' if draft_text else 'Pending'} {subject} — *{sender}*",
                    expanded=bool(draft_text),
                ):
                    st.markdown(
                        f'<p style="color: var(--white-muted); font-size: 0.9rem;">'
                        f'{_priority_badge_html(triage_t.get("priority", "unknown"))} '
                        f'<strong>Reason:</strong> {reason}'
                        f'</p>',
                        unsafe_allow_html=True,
                    )

                    # Side-by-side columns: thread ↔ draft
                    col_left, col_right = st.columns(2)

                    with col_left:
                        st.markdown("**Thread (latest message)**")
                        if pipeline_t and pipeline_t.get("messages"):
                            # Show only the last message for brevity
                            last_msg = pipeline_t["messages"][-1]
                            st.markdown(
                                f'<div class="thread-message">'
                                f'<div class="msg-header"><strong>{last_msg["from"]}</strong> &middot; {last_msg["date"]}</div>'
                                f'<div class="msg-body">{last_msg["body"].replace(chr(10), "<br>")}</div>'
                                f"</div>",
                                unsafe_allow_html=True,
                            )
                        elif pipeline_t:
                            st.markdown(
                                _render_thread_detail(pipeline_t),
                                unsafe_allow_html=True,
                            )
                        else:
                            st.caption("(thread data not available)")

                    with col_right:
                        st.markdown("**AI-Generated Draft**")

                        if draft_text:
                            st.markdown(
                                f'<div class="draft-box">{draft_text}</div>',
                                unsafe_allow_html=True,
                            )
                        else:
                            # Individual generate button
                            if st.button(
                                f"Generate Draft",
                                key=f"gen_single_{idx}_{thread_key}",
                                type="primary",
                                use_container_width=True,
                            ):
                                if pipeline_t is None:
                                    st.error("Thread data not found.")
                                else:
                                    with st.spinner("Generating draft…"):
                                        try:
                                            text = draft_reply(pipeline_t)
                                            st.session_state.drafts[thread_key] = text
                                            st.rerun()
                                        except Exception as e:
                                            st.error(
                                                f"Failed: {e}"
                                            )

            st.markdown("---")
            if st.session_state.drafts:
                st.info(
                    "Drafts are ready for review. Go to **Approval Gate** "
                    "to approve, edit, or reject each one."
                )


# ── PHASE 3: Approval Gate ───────────────────────────────────────────────────

elif st.session_state.current_phase == "Approval Gate":

    st.header("Approval Gate")

    if not st.session_state.drafts:
        st.info(
            "No drafts generated yet. Go to **Draft Generation** to create some."
        )
    else:
        # ── Pipeline Execution Log ───────────────────────────────────────────
        if st.session_state.pipeline_log:
            with st.expander("Pipeline Execution Log", expanded=False):
                for entry in st.session_state.pipeline_log:
                    if "ERROR" in entry or "FAILED" in entry:
                        st.markdown(f"[ERROR] {entry}")
                    else:
                        st.markdown(f"[SUCCESS] {entry}")

                if st.button("Clear log", key="clear_pipeline_log"):
                    st.session_state.pipeline_log = []
                    st.rerun()

            st.markdown("---")

        # ── Running count ───────────────────────────────────────────────────
        total = len(st.session_state.drafts)
        approved_count = len(st.session_state.approved)
        rejected_count = len(st.session_state.rejected)
        pending_count = total - approved_count - rejected_count

        count_col1, count_col2, count_col3 = st.columns(3)
        with count_col1:
            st.markdown(
                f'<div class="actionable-card">'
                f'<div class="actionable-count" style="color: var(--red-orange);">{approved_count}</div>'
                f'<div class="actionable-label">Approved</div>'
                f'</div>',
                unsafe_allow_html=True,
            )
        with count_col2:
            st.markdown(
                f'<div class="actionable-card">'
                f'<div class="actionable-count" style="color: var(--white-muted);">{rejected_count}</div>'
                f'<div class="actionable-label">Rejected</div>'
                f'</div>',
                unsafe_allow_html=True,
            )
        with count_col3:
            st.markdown(
                f'<div class="actionable-card">'
                f'<div class="actionable-count" style="color: var(--white);">{pending_count}</div>'
                f'<div class="actionable-label">Pending</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

        # ── Balloons when all reviewed ──────────────────────────────────────
        all_reviewed = pending_count == 0 and total > 0
        if all_reviewed:
            st.balloons()
            st.success(
                "All drafts reviewed! Head over to **Export Proof** "
                "to download or copy the approved drafts."
            )
            st.markdown("---")

        # ── Per-draft review cards ──────────────────────────────────────────
        for thread_key, draft_text in list(st.session_state.drafts.items()):
            is_approved = thread_key in st.session_state.approved
            is_rejected = thread_key in st.session_state.rejected

            status_emoji = "Approved" if is_approved else "Rejected" if is_rejected else "Pending"
            status_text = "Approved" if is_approved else "Rejected" if is_rejected else "Pending"

            with st.expander(
                f"{status_emoji} {thread_key} — *{status_text}*",
                expanded=not (is_approved or is_rejected),
            ):
                # Find the pipeline thread for context
                pipeline_thread = None
                for pt in st.session_state.threads:
                    if pt.get("subject") == thread_key:
                        pipeline_thread = pt
                        break

                # Find the triage data for category check
                triage_thread = None
                for tt in st.session_state.triaged:
                    if tt.get("subject") == thread_key:
                        triage_thread = tt
                        break

                col_left, col_right = st.columns(2)

                # ── LEFT: Full original thread ──────────────────────────────
                with col_left:
                    st.markdown("**Full Original Thread**")
                    if pipeline_thread:
                        st.markdown(
                            _render_thread_detail(pipeline_thread),
                            unsafe_allow_html=True,
                        )
                    else:
                        st.caption("(thread data not available)")

                # ── RIGHT: Editable draft + actions ─────────────────────────
                with col_right:
                    st.markdown("**Draft (editable)**")

                    if is_approved:
                        st.markdown(
                            f'<div class="draft-box">{draft_text}</div>',
                            unsafe_allow_html=True,
                        )
                        st.markdown(
                            '<div class="status-approved">Approved</div>',
                            unsafe_allow_html=True,
                        )
                        if st.button(
                            "Unapprove",
                            key=f"unapprove_{thread_key}",
                            use_container_width=True,
                        ):
                            del st.session_state.approved[thread_key]
                            st.rerun()

                        # Check if this is a meeting-request and show Book Meeting button
                        is_meeting_request = triage_thread and triage_thread.get(
                            "category") == "meeting-request"
                        is_sent = thread_key in st.session_state.sent
                        is_booked = thread_key in st.session_state.booked

                        if is_meeting_request:
                            st.markdown("---")
                            if is_booked:
                                # Show calendar link if already booked
                                event = st.session_state.booked[thread_key]
                                html_link = event.get("htmlLink", "")
                                st.markdown(
                                    f'<div class="status-approved">Meeting Booked</div>',
                                    unsafe_allow_html=True,
                                )
                                if html_link:
                                    st.markdown(
                                        f'<a href="{html_link}" target="_blank" style="color: var(--red-orange);">View in Google Calendar</a>',
                                        unsafe_allow_html=True,
                                    )
                            else:
                                # Show Send and Book Meeting buttons side by side
                                col_send, col_book = st.columns(2)

                                with col_send:
                                    has_gmail_data = bool(
                                        pipeline_thread and pipeline_thread.get("thread_id"))
                                    send_disabled = is_sent or not has_gmail_data
                                    send_label = "Sent" if is_sent else "Send"

                                    if st.button(
                                        send_label,
                                        key=f"send_approval_{thread_key}",
                                        use_container_width=True,
                                        type="primary" if not is_sent else "secondary",
                                        disabled=send_disabled,
                                    ):
                                        if pipeline_thread is None:
                                            st.error("Thread data not found.")
                                        elif not has_gmail_data:
                                            st.error(
                                                "No Gmail thread ID available.")
                                        else:
                                            try:
                                                subject_line = thread_key
                                                if not subject_line.startswith("Re:"):
                                                    subject_line = f"Re: {subject_line}"

                                                resp = send_reply(
                                                    thread_id=pipeline_thread.get(
                                                        "thread_id", ""),
                                                    reply_body=draft_text,
                                                    to=pipeline_thread["messages"][-1].get(
                                                        "from", "") if pipeline_thread.get("messages") else "",
                                                    subject=subject_line,
                                                    references=pipeline_thread.get(
                                                        "references", ""),
                                                    in_reply_to=pipeline_thread.get(
                                                        "in_reply_to", ""),
                                                )
                                                st.session_state.sent.add(
                                                    thread_key)
                                                st.success(
                                                    f"Sent! Gmail message ID: {resp.get('id', 'unknown')}")
                                                recipient = pipeline_thread["messages"][-1].get(
                                                    "from", "") if pipeline_thread.get("messages") else ""
                                                log_action(
                                                    action_type="sent",
                                                    thread_subject=thread_key,
                                                    detail=recipient,
                                                    action_id=resp.get(
                                                        "id", "unknown"),
                                                )
                                                st.rerun()
                                            except Exception as e:
                                                st.error(
                                                    f"Failed to send: {e}")

                                with col_book:
                                    book_key = f"book_{thread_key}"
                                    if st.button(
                                        "Book Meeting",
                                        key=book_key,
                                        type="primary",
                                        use_container_width=True,
                                    ):
                                        if pipeline_thread is None:
                                            st.error("Thread data not found.")
                                        else:
                                            calendar_engine = _get_calendar_engine()

                                            # Step 1: Parse meeting request
                                            with st.spinner("Parsing meeting details..."):
                                                try:
                                                    meeting_details = calendar_engine.parse_meeting_request(
                                                        pipeline_thread)
                                                    if "parsing_error" in meeting_details:
                                                        st.error(
                                                            f"Failed to parse meeting: {meeting_details['parsing_error']}")
                                                    else:
                                                        # Show extracted details
                                                        proposed_times = meeting_details.get(
                                                            "proposed_times", [])
                                                        st.info(
                                                            f"**Topic:** {meeting_details.get('topic', 'N/A')}\n"
                                                            f"**Duration:** {meeting_details.get('duration_minutes', 30)} minutes\n"
                                                            f"**Proposed times:** {len(proposed_times)} option(s)\n"
                                                            f"**Attendees:** {', '.join(meeting_details.get('attendees', [])) or 'None specified'}"
                                                        )

                                                        # Debug: show the actual proposed times
                                                        if proposed_times:
                                                            st.markdown(
                                                                "**Proposed times being checked:**")
                                                            for i, time_str in enumerate(proposed_times, 1):
                                                                st.markdown(
                                                                    f"{i}. `{time_str}`")

                                                        # Step 2: Find free slot
                                                        with st.spinner("Checking availability..."):
                                                            duration = meeting_details.get(
                                                                "duration_minutes", 30)

                                                            if not proposed_times:
                                                                st.error(
                                                                    "No proposed times found in the email.")
                                                            else:
                                                                # Manually check each slot and show results
                                                                import datetime as dt
                                                                st.markdown(
                                                                    "**Availability check results:**")
                                                                all_busy = True

                                                                for idx, time_str in enumerate(proposed_times):
                                                                    try:
                                                                        # Parse the start time
                                                                        if time_str.endswith("Z"):
                                                                            start_time = dt.datetime.fromisoformat(
                                                                                time_str.replace("Z", "+00:00"))
                                                                        else:
                                                                            start_time = dt.datetime.fromisoformat(
                                                                                time_str)

                                                                        # Calculate end time
                                                                        end_time = start_time + \
                                                                            dt.timedelta(
                                                                                minutes=duration)

                                                                        # Convert back to ISO-8601 strings
                                                                        time_min = start_time.isoformat()
                                                                        time_max = end_time.isoformat()

                                                                        # Check availability
                                                                        is_free = calendar_engine.check_availability(
                                                                            time_min, time_max)

                                                                        status = "Free" if is_free else "Busy"
                                                                        st.markdown(
                                                                            f"{idx + 1}. `{time_str}` → {status}")

                                                                        if is_free:
                                                                            all_busy = False
                                                                    except Exception as e:
                                                                        st.markdown(
                                                                            f"{idx + 1}. `{time_str}` → Error: {e}")

                                                                if all_busy:
                                                                    st.error(
                                                                        "No available time slots found for the proposed times.")
                                                                    st.markdown(
                                                                        "**Debug info:** All proposed times returned as busy. This could mean:")
                                                                    st.markdown(
                                                                        "- The times are in the past")
                                                                    st.markdown(
                                                                        "- Your calendar already has events at those times")
                                                                    st.markdown(
                                                                        "- The time format couldn't be parsed correctly")

                                                                    # Try to find alternative slots
                                                                    with st.spinner("Looking for alternative time slots..."):
                                                                        alternatives = calendar_engine.find_alternative_slots(
                                                                            proposed_times, duration)
                                                                        if alternatives:
                                                                            st.markdown(
                                                                                f"**Found {len(alternatives)} alternative time slot(s):**")
                                                                            import datetime as dt
                                                                            for i, alt_time in enumerate(alternatives, 1):
                                                                                # Format the time for display
                                                                                try:
                                                                                    if alt_time.endswith("Z"):
                                                                                        dt_obj = dt.datetime.fromisoformat(
                                                                                            alt_time.replace("Z", "+00:00"))
                                                                                    else:
                                                                                        dt_obj = dt.datetime.fromisoformat(
                                                                                            alt_time)
                                                                                    formatted_time = dt_obj.strftime(
                                                                                        "%B %d, %Y at %I:%M %p")
                                                                                except:
                                                                                    formatted_time = alt_time

                                                                                col_alt, col_book_alt = st.columns(
                                                                                    [3, 1])
                                                                                with col_alt:
                                                                                    st.markdown(
                                                                                        f"**{i}.** {formatted_time}")
                                                                                with col_book_alt:
                                                                                    if st.button(
                                                                                        "Book",
                                                                                        key=f"book_alt_{i}_{thread_key}",
                                                                                        type="primary",
                                                                                        use_container_width=True,
                                                                                    ):
                                                                                        try:
                                                                                            event = calendar_engine.create_event(
                                                                                                summary=meeting_details.get(
                                                                                                    "topic", "Meeting"),
                                                                                                start_time=alt_time,
                                                                                                duration_minutes=duration,
                                                                                                attendees=meeting_details.get(
                                                                                                    "attendees", []),
                                                                                                description=f"Created from email: {thread_key}"
                                                                                            )
                                                                                            st.session_state.booked[
                                                                                                thread_key] = event
                                                                                            html_link = event.get(
                                                                                                "htmlLink", "")
                                                                                            st.success(
                                                                                                f"Meeting booked successfully!\n"
                                                                                                f"**Time:** {formatted_time}\n"
                                                                                                f"**Event ID:** {event.get('id', 'unknown')}"
                                                                                            )
                                                                                            if html_link:
                                                                                                st.markdown(
                                                                                                    f'<a href="{html_link}" target="_blank" style="color: var(--red-orange);">View in Google Calendar</a>',
                                                                                                    unsafe_allow_html=True,
                                                                                                )
                                                                                            log_action(
                                                                                                action_type="booked",
                                                                                                thread_subject=thread_key,
                                                                                                detail=meeting_details.get(
                                                                                                    "topic", thread_key),
                                                                                                action_id=event.get(
                                                                                                    "id", "unknown"),
                                                                                            )
                                                                                            st.rerun()
                                                                                        except Exception as e:
                                                                                            st.error(
                                                                                                f"Failed to create calendar event: {e}")
                                                                else:
                                                                    # Now run the actual find_free_slot to get the first available
                                                                    free_slot = calendar_engine.find_free_slot(
                                                                        proposed_times, duration)

                                                                    if free_slot is None:
                                                                        st.error(
                                                                            "No available time slots found for the proposed times.")
                                                                    else:
                                                                        # Step 3: Create event
                                                                        with st.spinner("Creating calendar event..."):
                                                                            try:
                                                                                event = calendar_engine.create_event(
                                                                                    summary=meeting_details.get(
                                                                                        "topic", "Meeting"),
                                                                                    start_time=free_slot,
                                                                                    duration_minutes=duration,
                                                                                    attendees=meeting_details.get(
                                                                                        "attendees", []),
                                                                                    description=f"Created from email: {thread_key}"
                                                                                )

                                                                                # Store in session state
                                                                                st.session_state.booked[thread_key] = event

                                                                                # Show success with calendar link
                                                                                html_link = event.get(
                                                                                    "htmlLink", "")
                                                                                st.success(
                                                                                    f"Meeting booked successfully!\n"
                                                                                    f"**Time:** {free_slot}\n"
                                                                                    f"**Event ID:** {event.get('id', 'unknown')}"
                                                                                )
                                                                                if html_link:
                                                                                    st.markdown(
                                                                                        f'<a href="{html_link}" target="_blank" style="color: var(--red-orange);">View in Google Calendar</a>',
                                                                                        unsafe_allow_html=True,
                                                                                    )
                                                                                log_action(
                                                                                    action_type="booked",
                                                                                    thread_subject=thread_key,
                                                                                    detail=meeting_details.get(
                                                                                        "topic", thread_key),
                                                                                    action_id=event.get(
                                                                                        "id", "unknown"),
                                                                                )
                                                                                st.rerun()
                                                                            except Exception as e:
                                                                                st.error(
                                                                                    f"Failed to create calendar event: {e}")
                                                except Exception as e:
                                                    st.error(
                                                        f"Error during meeting booking: {e}")

                    elif is_rejected:
                        st.markdown(
                            f'<div class="draft-box">{draft_text}</div>',
                            unsafe_allow_html=True,
                        )
                        st.markdown(
                            '<div class="status-rejected">Rejected</div>',
                            unsafe_allow_html=True,
                        )
                        if st.button(
                            "Undo Reject",
                            key=f"undoreject_{thread_key}",
                            use_container_width=True,
                        ):
                            st.session_state.rejected.discard(thread_key)
                            st.rerun()

                    else:
                        # ── Pending: editable text_area + 3 buttons ─────────
                        # Use a session key per thread to preserve edit state
                        edit_key = f"approval_edit_{thread_key}"
                        current_edit = st.session_state.get(
                            edit_key, draft_text)

                        edited = st.text_area(
                            "Edit the draft before approving:",
                            value=current_edit,
                            height=250,
                            key=edit_key,
                        )

                        a_col1, a_col2, a_col3 = st.columns(3)
                        with a_col1:
                            if st.button(
                                "Approve",
                                type="primary",
                                use_container_width=True,
                                key=f"approve_{thread_key}",
                            ):
                                # Save the edited text, not the original
                                saved_text = st.session_state.get(
                                    edit_key, draft_text
                                )
                                st.session_state.approved[thread_key] = saved_text
                                st.session_state.drafts[thread_key] = saved_text
                                st.rerun()

                        with a_col2:
                            if st.button(
                                "Regenerate",
                                use_container_width=True,
                                key=f"regen_{thread_key}",
                            ):
                                if pipeline_thread is None:
                                    st.error("Thread data not found.")
                                else:
                                    with st.spinner("Regenerating draft…"):
                                        try:
                                            new_draft = draft_reply(
                                                pipeline_thread)
                                            st.session_state.drafts[thread_key] = new_draft
                                            # Reset the edit text area
                                            if edit_key in st.session_state:
                                                del st.session_state[edit_key]
                                            st.rerun()
                                        except Exception as e:
                                            st.error(
                                                f"Regeneration failed: {e}")

                        with a_col3:
                            if st.button(
                                "Reject",
                                use_container_width=True,
                                key=f"reject_{thread_key}",
                            ):
                                st.session_state.rejected.add(thread_key)
                                st.rerun()


# ── PHASE 4: Export Proof ────────────────────────────────────────────────────

elif st.session_state.current_phase == "Export Proof":

    st.header("Export Proof")

    if not st.session_state.approved:
        st.info(
            "No approved drafts yet. Go to **Approval Gate** to approve some drafts."
        )
    else:
        st.markdown(
            f"<p style='color: var(--white-muted);'>"
            f"{len(st.session_state.approved)} approved draft{'s' if len(st.session_state.approved) != 1 else ''} ready for export."
            f"</p>",
            unsafe_allow_html=True,
        )

        # Build export data with full thread messages for proof generation
        export_data = []
        for thread_key, draft_text in st.session_state.approved.items():
            # Find the pipeline thread for metadata and messages
            pipeline_thread = None
            for pt in st.session_state.threads:
                if pt.get("subject") == thread_key:
                    pipeline_thread = pt
                    break

            last_from = ""
            messages = []
            gmail_thread_id = ""
            gmail_refs = ""
            gmail_in_reply_to = ""
            if pipeline_thread and pipeline_thread.get("messages"):
                last_from = pipeline_thread["messages"][-1].get("from", "")
                messages = pipeline_thread["messages"]
                gmail_thread_id = pipeline_thread.get("thread_id", "")
                gmail_refs = pipeline_thread.get("references", "")
                gmail_in_reply_to = pipeline_thread.get("in_reply_to", "")

            export_data.append({
                "subject": thread_key,
                "replying_to": last_from,
                "draft": draft_text,
                "messages": messages,
                "gmail_thread_id": gmail_thread_id,
                "gmail_refs": gmail_refs,
                "gmail_in_reply_to": gmail_in_reply_to,
            })

        # ── Side-by-side preview for each approved draft ──────────────────
        st.subheader("Approved Drafts — Side-by-Side Preview")
        st.markdown(
            '<p style="color: var(--white-muted); margin-top: -8px; margin-bottom: 20px;">'
            "Original thread (left) &nbsp;|&nbsp; Approved draft (right)"
            "</p>",
            unsafe_allow_html=True,
        )

        for item in export_data:
            with st.expander(f"{item['subject']}", expanded=True):
                col_left, col_right = st.columns(2)

                with col_left:
                    st.markdown(
                        '<p style="color: var(--white-soft); font-weight: 700; margin-bottom: 8px;">Original Thread</p>',
                        unsafe_allow_html=True,
                    )
                    if item["messages"]:
                        for msg in item["messages"]:
                            st.markdown(
                                f'<div class="thread-message">'
                                f'<div class="msg-header"><strong>{msg["from"]}</strong> &middot; {msg["date"]}</div>'
                                f'<div class="msg-body">{msg["body"].replace(chr(10), "<br>")}</div>'
                                f"</div>",
                                unsafe_allow_html=True,
                            )
                    else:
                        st.caption("(thread data not available)")

                with col_right:
                    st.markdown(
                        '<p style="color: var(--white-soft); font-weight: 700; margin-bottom: 8px;">Approved Draft</p>',
                        unsafe_allow_html=True,
                    )
                    st.markdown(
                        f'<div class="draft-box" style="border-color: var(--red-orange);">{item["draft"]}</div>',
                        unsafe_allow_html=True,
                    )

        # ── Send to Gmail section ─────────────────────────────────────────
        st.markdown("---")
        st.subheader("Send Approved Drafts")

        if st.session_state.source != "Gmail (via engine.py)":
            st.info(
                "Switch the email source to **Gmail (via engine.py)** in the sidebar "
                "to enable sending. Sample threads don't have real Gmail message IDs."
            )
        else:
            st.markdown(
                '<p style="color: var(--white-muted); margin-top: -8px; margin-bottom: 12px;">'
                "Each approved draft can be sent as a reply to its original Gmail thread."
                "</p>",
                unsafe_allow_html=True,
            )

            for item in export_data:
                thread_key = item["subject"]
                is_sent = thread_key in st.session_state.sent
                has_gmail_data = bool(item["gmail_thread_id"])

                if not has_gmail_data:
                    continue

                with st.container():
                    st.markdown(
                        f'<p style="margin-bottom: 4px;"><strong>{thread_key}</strong></p>',
                        unsafe_allow_html=True,
                    )

                    col_send, col_status = st.columns([1, 3])
                    with col_send:
                        send_label = "Sent" if is_sent else "Send to Gmail"
                        send_disabled = is_sent
                        if st.button(
                            send_label,
                            key=f"send_{thread_key}",
                            use_container_width=True,
                            type="primary" if not is_sent else "secondary",
                            disabled=send_disabled,
                        ):
                            try:
                                subject_line = item["subject"]
                                if not subject_line.startswith("Re:"):
                                    subject_line = f"Re: {subject_line}"

                                resp = send_reply(
                                    thread_id=item["gmail_thread_id"],
                                    reply_body=item["draft"],
                                    to=item["replying_to"],
                                    subject=subject_line,
                                    references=item.get("gmail_refs", ""),
                                    in_reply_to=item.get(
                                        "gmail_in_reply_to", ""),
                                )
                                st.session_state.sent.add(thread_key)
                                st.success(
                                    f"Sent! Gmail message ID: {resp.get('id', 'unknown')}"
                                )
                                st.rerun()
                            except Exception as e:
                                st.error(f"Failed to send: {e}")

                    with col_status:
                        if is_sent:
                            st.markdown(
                                '<span class="status-approved">Sent successfully via Gmail API</span>',
                                unsafe_allow_html=True,
                            )

                st.markdown("---")

        # ── Download buttons ──────────────────────────────────────────────
        st.subheader("Download Proof of Work")

        col_md, col_html = st.columns(2)

        with col_md:
            md_content = generate_proof_markdown(export_data)
            st.download_button(
                label="Download Proof (Markdown)",
                data=md_content,
                file_name="proof_of_work.md",
                mime="text/markdown",
                type="primary",
                use_container_width=True,
            )

        with col_html:
            html_content = generate_proof_html(export_data)
            st.download_button(
                label="Download Proof (HTML)",
                data=html_content,
                file_name="proof_of_work.html",
                mime="text/html",
                type="primary",
                use_container_width=True,
            )

        # ── Action Log ──────────────────────────────────────────────────────
        st.markdown("---")
        st.subheader("Action Log")

        action_log = get_action_log()
        if not action_log:
            st.info("No actions logged yet.")
        else:
            for entry in action_log:
                icon = "[SENT]" if entry.get("action_type") == "sent" else "[BOOKED]"
                action_label = entry.get("action_type", "").upper()
                col1, col2, col3, col4 = st.columns([1, 3, 3, 2])
                with col1:
                    st.markdown(f"{icon} **{action_label}**")
                with col2:
                    st.markdown(f"**{entry.get('thread_subject', '')}**")
                with col3:
                    st.markdown(f"`{entry.get('detail', '')}`")
                with col4:
                    try:
                        from datetime import datetime
                        ts = datetime.fromisoformat(entry.get("timestamp", ""))
                        st.caption(ts.strftime("%b %d %I:%M %p"))
                    except Exception:
                        st.caption(entry.get("timestamp", ""))

# ── Footer ────────────────────────────────────────────────────────────────────

st.markdown("---")
st.markdown(
    '<p style="text-align: center; color: var(--white-muted); font-size: 0.8rem; letter-spacing: 0.5px;">'
    "Human-in-the-loop guardrail active — nothing is sent without your approval."
    "</p>",
    unsafe_allow_html=True,
)
