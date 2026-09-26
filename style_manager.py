import json
import os

STYLE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "user_style.json")

DEFAULT_STYLE = {
    "verbosity": "concise",
    "tone": "formal_official",
    "paragraph_length": "short",
    "uses_abbreviations": True,
    "reference_style": "BAF_standard",
    "preferred_closing": "This is sent for your info and nec act pl.",
    "avoid_phrases": ["It is most respectfully stated that"],
    "edit_count_history": {}
}

# Plan Section 65.1 — threshold rule:
# 1 edit    → suggestion only (do NOT update style yet)
# 3+ edits  → preference proposed (flag as candidate)
# 5+ edits  → auto-apply candidate
THRESHOLD_SUGGEST  = 1
THRESHOLD_PROPOSE  = 3
THRESHOLD_APPLY    = 5


def load_user_style():
    if not os.path.exists(STYLE_FILE):
        save_user_style(DEFAULT_STYLE)
        return DEFAULT_STYLE
    with open(STYLE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_user_style(style_data):
    with open(STYLE_FILE, "w", encoding="utf-8") as f:
        json.dump(style_data, f, indent=2, ensure_ascii=False)


def update_preference(key, value, force=False):
    """
    Update the user's style preference based on edit count thresholds.

    Returns a dict describing what action was taken:
      status: 'suggestion' | 'proposed' | 'applied'
    """
    style = load_user_style()
    history = style.get("edit_count_history", {})
    history[key] = history.get(key, 0) + 1
    style["edit_count_history"] = history

    count = history[key]

    if force or count >= THRESHOLD_APPLY:
        style[key] = value
        status = "applied"
    elif count >= THRESHOLD_PROPOSE:
        # Mark as a pending candidate — record it but don't apply yet
        pending = style.get("pending_preferences", {})
        pending[key] = value
        style["pending_preferences"] = pending
        status = "proposed"
    else:
        # Only 1 edit — record the edit count but do not apply
        status = "suggestion"

    save_user_style(style)
    return {"key": key, "value": value, "edit_count": count, "status": status}


def accept_pending_preference(key):
    """User manually accepts a proposed preference."""
    style = load_user_style()
    pending = style.get("pending_preferences", {})
    if key in pending:
        style[key] = pending.pop(key)
        style["pending_preferences"] = pending
        save_user_style(style)
        return True
    return False


def get_style_prompt_summary():
    style = load_user_style()
    summary = (
        f"USER WRITING PREFERENCES:\n"
        f"- Verbosity: {style.get('verbosity')}\n"
        f"- Tone: {style.get('tone')}\n"
        f"- Paragraph length: {style.get('paragraph_length')}\n"
        f"- Closing: {style.get('preferred_closing')}\n"
    )
    if style.get("avoid_phrases"):
        summary += f"- Avoid phrases: {', '.join(style.get('avoid_phrases'))}\n"
    pending = style.get("pending_preferences", {})
    if pending:
        summary += f"- Proposed (not yet applied): {pending}\n"
    return summary
