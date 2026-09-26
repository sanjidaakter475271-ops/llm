import sqlite3
import json
import os
import difflib
import time
from style_manager import update_preference

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "letter_memory.db")

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Versions table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS letter_versions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        letter_id TEXT,
        version_no INTEGER,
        content TEXT,
        change_reason TEXT,
        approved INTEGER,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """)
    
    # Learning memory table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS learning_memory (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        letter_id TEXT,
        original_content TEXT,
        final_content TEXT,
        detected_changes TEXT,
        approved_by_user INTEGER,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """)
    
    conn.commit()
    conn.close()

init_db()

def compare_letters(original_text, final_text):
    """
    Compares original AI version with user's final edited version.
    Returns detected changes summary.
    """
    orig_words = len(original_text.split())
    final_words = len(final_text.split())
    
    diff = list(difflib.ndiff(original_text.splitlines(), final_text.splitlines()))
    
    changes = []
    if final_words < orig_words * 0.85:
        changes.append({"key": "verbosity", "detected": "concise", "desc": "User preferred shorter, more concise phrasing."})
    elif final_words > orig_words * 1.15:
        changes.append({"key": "verbosity", "detected": "detailed", "desc": "User added more details/elaboration."})
        
    removed_lines = [line[2:] for line in diff if line.startswith('- ')]
    added_lines = [line[2:] for line in diff if line.startswith('+ ')]
    
    if removed_lines:
        for rem in removed_lines:
            if "respectfully" in rem.lower():
                changes.append({"key": "avoid_phrase", "detected": rem, "desc": "Removed overly formal/verbose phrase."})
                
    return {
        "word_diff": final_words - orig_words,
        "changes": changes,
        "raw_diff": [line for line in diff if line.startswith('+ ') or line.startswith('- ')]
    }

def log_version(letter_id, version_no, content, change_reason="", approved=False):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO letter_versions (letter_id, version_no, content, change_reason, approved) VALUES (?, ?, ?, ?, ?)",
        (letter_id, version_no, json.dumps(content, ensure_ascii=False), change_reason, 1 if approved else 0)
    )
    conn.commit()
    conn.close()

def log_learning_event(letter_id, original_json, final_json, approved=True):
    orig_str = json.dumps(original_json, ensure_ascii=False)
    final_str = json.dumps(final_json, ensure_ascii=False)
    
    comparison = compare_letters(orig_str, final_str)
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO learning_memory (letter_id, original_content, final_content, detected_changes, approved_by_user) VALUES (?, ?, ?, ?, ?)",
        (letter_id, orig_str, final_str, json.dumps(comparison["changes"], ensure_ascii=False), 1 if approved else 0)
    )
    conn.commit()
    conn.close()
    
    return comparison

def apply_user_feedback(change_item, accept=True):
    if accept:
        update_preference(change_item["key"], change_item["detected"])
        return True
    return False
