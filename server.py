"""
BAF Letter Generator Server v2
================================
Run: py server.py
Opens on: http://localhost:5050

Fixes:
- Classification now uses user input exactly (not hardcoded RESTRICTED)
- Priority now uses user input exactly
- Rank and Appointment are passed through unchanged — AI cannot modify them
- Classification appears in header/footer on every page (via generate_letter.js)
"""

import json, os, subprocess, tempfile, re, time
from http.server import HTTPServer, BaseHTTPRequestHandler
import requests

from abbreviation_helper import get_relevant_abbreviations
from letter_retriever import retrieve_similar_letters
from policy_retriever import search_policy
from style_manager import get_style_prompt_summary, accept_pending_preference
from validator import validate_letter_json
from learning_center import log_version, log_learning_event
from dataset_builder import init_dataset_structure
from evaluation_harness import create_sample_golden_tests

OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL      = "qwen3.5:9b"
PORT       = 5050
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
GEN_SCRIPT = os.path.join(SCRIPT_DIR, "generate_letter.js")


def call_ollama(messages):
    payload = {
        "model": MODEL,
        "messages": messages,
        "stream": False,
        "think": False,
        "options": {"num_predict": 1200, "temperature": 0.2}
    }
    r = requests.post(OLLAMA_URL, json=payload, timeout=180)
    r.raise_for_status()
    content = r.json()["message"]["content"].strip()
    content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()
    return content


def generate_letter_json(letter_type, user_data):
    """
    Strategy: AI only generates subject + body.
    All other fields come DIRECTLY from user input — AI cannot touch them.
    This prevents AI from overriding classification, priority, rank, appointment.
    Integrated with RAG (Similar Letters + Policy) and User Style Memory.
    """

    type_names = {
        "rl": "Routine Letter", "lm": "Loose Minute",
        "dl": "Directed Letter", "cl": "Commanded Letter",
        "fl": "Formal Letter",   "do": "Demi-Official Letter",
        "mem": "Memorandum"
    }
    type_name = type_names.get(letter_type, "Routine Letter")

    situation = user_data.get('situation', '')

    # 1. Retrieve relevant abbreviations
    abbr_text = get_relevant_abbreviations(situation, limit=25)

    # 2. Retrieve similar previous letters
    similar_docs = retrieve_similar_letters(situation, letter_type=letter_type, top_k=2)
    example_text = ""
    if similar_docs:
        example_text = "EXAMPLE PREVIOUS APPROVED LETTERS FOR REFERENCE:\n"
        for i, doc in enumerate(similar_docs):
            example_text += f"Example {i+1}:\nSubject: {doc.get('subject')}\nBody: {' '.join(doc.get('body', []))}\n\n"

    # 3. Retrieve user style memory
    style_summary = get_style_prompt_summary()

    # 4. Construct System Prompt dynamically
    system_prompt = f"""You are a Bangladesh Air Force (BAF) military letter writing assistant.
You write letters strictly following JSSDM format.
You write in formal military style — concise, clear, third person.

{style_summary}

KEY RELEVANT ABBREVIATIONS:
{abbr_text}

CRITICAL RULES:
- Generate ONLY the subject line and body paragraphs
- Do NOT change, correct, or reformat any field given to you
- Last paragraph ends with "This is sent for your info and nec act pl." or similar
- Return ONLY valid JSON, no markdown, no extra text"""

    # Parse list fields from newline-separated strings
    def parse_list(val):
        if not val:
            return []
        if isinstance(val, list):
            return val
        return [x.strip() for x in str(val).split('\n') if x.strip()]

    def parse_refs(val):
        if not val:
            return []
        if isinstance(val, list):
            items = val
        else:
            items = [x.strip() for x in str(val).split('\n') if x.strip()]
        cleaned = []
        for item in items:
            item_clean = re.sub(r'^(refs?[:\s]*)+', '', item, flags=re.IGNORECASE).strip()
            item_clean = re.sub(r'^[A-Z]\.\s*', '', item_clean).strip()
            if item_clean and item_clean not in cleaned:
                cleaned.append(item_clean)
        return cleaned

    # ── Ask AI only for subject + body ──────────────────────────
    prompt = f"""Generate a BAF {type_name} subject line and body paragraphs only.

SITUATION: {situation}

{example_text}

Return ONLY this JSON structure:
{{
  "subject": "SUBJECT LINE IN CAPS",
  "body": [
    "First paragraph using BAF abbreviations",
    {{"text": "Second paragraph with sub-items", "subItems": ["sub item a text", "sub item b text"]}},
    "Final paragraph — This is sent for your info and nec act pl."
  ]
}}"""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user",   "content": prompt}
    ]

    raw = call_ollama(messages)
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"```[a-z]*\n?", "", raw).strip()
    if raw.endswith("```"):
        raw = raw[:-3].strip()

    ai_content = json.loads(raw)

    # ── Build final letter JSON — user fields are NEVER touched by AI ──
    classification = user_data.get('classification', 'RESTRICTED').strip()
    if not classification:
        classification = 'RESTRICTED'

    priority = user_data.get('priority', '').strip()

    letter_json = {
        "type":           letter_type,

        # ── User fields — passed through exactly as entered ──────
        "classification": classification,
        "priority":       priority,
        "unit":           user_data.get('unit', '').strip(),
        "branch":         user_data.get('branch', '').strip(),
        "dte":            user_data.get('dte', '').strip(),
        "address":        user_data.get('address', '').strip(),
        "tel":            user_data.get('tel', '').strip(),
        "email":          user_data.get('email', '').strip(),
        "fileRef":        user_data.get('fileRef', '').strip(),
        "date":           user_data.get('date', '').strip(),

        # Rank and Appointment — EXACTLY as user typed, no changes
        "sigName":        user_data.get('sigName', '').strip(),
        "sigRank":        user_data.get('sigRank', '').strip(),
        "sigAppt":        user_data.get('sigAppt', '').strip(),
        "sigFor":         user_data.get('sigFor', '').strip(),

        # LM specific
        "lmRef":          user_data.get('lmRef', '').strip(),
        "ext":            user_data.get('ext', '').strip(),

        # Distribution lists
        "refs":           parse_refs(user_data.get('refs', '')),
        "extlAct":        parse_list(user_data.get('extlAct', '')),
        "extlInfo":       parse_list(user_data.get('extlInfo', '')),
        "intlAct":        parse_list(user_data.get('intlAct', '')),
        "intlInfo":       parse_list(user_data.get('intlInfo', '')),
        "to":             parse_list(user_data.get('to', '')),
        "info":           parse_list(user_data.get('info', '')),

        # ── AI generated fields ──────────────────────────────────
        "subject":        ai_content.get('subject', ''),
        "body":           ai_content.get('body', []),
    }

    # Validate output
    val_res = validate_letter_json(letter_json)
    final_json = val_res['normalized_json']
    
    # Log version history
    log_version(final_json.get('fileRef', 'draft'), 1, final_json, "Initial AI Generation", approved=False)

    return final_json


def run_node_generator(letter_json, out_path):
    """Run the Node.js generator to produce .docx"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json',
                                     delete=False, encoding='utf-8') as f:
        json.dump(letter_json, f, ensure_ascii=False)
        tmp_json = f.name
    try:
        result = subprocess.run(
            ['node', GEN_SCRIPT, tmp_json, out_path],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode != 0:
            raise Exception(result.stderr)
        return True
    finally:
        os.unlink(tmp_json)


HTML_PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>BAF Letter Generator</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600&display=swap');
  :root {
    --bg:#0b0f14;--surface:#111820;--border:#1e2d3d;
    --accent:#00bfff;--text:#cdd9e5;--muted:#4a6070;
    --success:#00e5a0;--error:#ff4d4d;
  }
  *{box-sizing:border-box;margin:0;padding:0}
  body{background:var(--bg);color:var(--text);font-family:'Inter',sans-serif;font-size:14px;min-height:100vh}
  header{background:var(--surface);border-bottom:1px solid var(--border);padding:14px 28px;display:flex;align-items:center;gap:16px}
  .badge{background:var(--accent);color:#000;font-weight:700;font-size:11px;letter-spacing:2px;padding:4px 10px;border-radius:2px}
  header h1{font-size:15px;font-weight:600;letter-spacing:1px}
  .wrap{max-width:900px;margin:0 auto;padding:28px 20px}
  .card{background:var(--surface);border:1px solid var(--border);border-radius:6px;padding:24px;margin-bottom:20px}
  .card h2{font-size:11px;letter-spacing:2px;color:var(--muted);text-transform:uppercase;margin-bottom:16px}
  .grid{display:grid;grid-template-columns:1fr 1fr;gap:14px}
  .full{grid-column:1/-1}
  label{display:block;font-size:11px;color:var(--muted);letter-spacing:1px;margin-bottom:5px;text-transform:uppercase}
  input,select,textarea{width:100%;background:var(--bg);border:1px solid var(--border);border-radius:4px;color:var(--text);font-family:'Inter',sans-serif;font-size:13px;padding:9px 12px;outline:none;transition:border-color .2s}
  input:focus,select:focus,textarea:focus{border-color:var(--accent)}
  textarea{resize:vertical;min-height:80px}
  select option{background:var(--surface)}
  .type-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-bottom:6px}
  .type-btn{background:var(--bg);border:1px solid var(--border);color:var(--muted);font-size:11px;letter-spacing:1px;padding:10px 6px;cursor:pointer;border-radius:4px;text-align:center;transition:all .2s}
  .type-btn:hover{border-color:var(--accent);color:var(--text)}
  .type-btn.active{background:#005f7f;border-color:var(--accent);color:var(--accent)}
  .run-btn{background:var(--accent);color:#000;border:none;border-radius:4px;font-weight:700;font-size:13px;letter-spacing:2px;padding:14px 28px;cursor:pointer;width:100%;transition:all .2s;margin-top:8px}
  .run-btn:hover{background:#33ccff}
  .run-btn:disabled{background:var(--muted);cursor:not-allowed}
  .status{padding:12px 16px;border-radius:4px;font-size:13px;margin-top:12px;display:none}
  .status.info{background:rgba(0,191,255,.1);border:1px solid var(--accent);color:var(--accent)}
  .status.ok{background:rgba(0,229,160,.1);border:1px solid var(--success);color:var(--success)}
  .status.err{background:rgba(255,77,77,.1);border:1px solid var(--error);color:var(--error)}
  .dl-btn{background:var(--success);color:#000;border:none;border-radius:4px;font-weight:700;font-size:13px;padding:12px 24px;cursor:pointer;display:none;margin-top:10px;width:100%}
  #section-lm-fields{display:none}
  #section-rl-fields{display:none}
</style>
</head>
<body>
<header>
  <div class="badge">BAF</div>
  <h1>LETTER WRITING ASSISTANT</h1>
</header>
<div class="wrap">

  <div class="card">
    <h2>Letter Type</h2>
    <div class="type-grid">
      <button class="type-btn active" onclick="setType('rl',event)">📄 Routine Letter</button>
      <button class="type-btn" onclick="setType('lm',event)">📋 Loose Minute</button>
      <button class="type-btn" onclick="setType('dl',event)">📑 Directed Letter</button>
      <button class="type-btn" onclick="setType('fl',event)">📜 Formal Letter</button>
      <button class="type-btn" onclick="setType('do',event)">✉️ Demi-Official</button>
      <button class="type-btn" onclick="setType('cl',event)">🏛️ Commanded</button>
      <button class="type-btn" onclick="setType('mem',event)">📝 Memorandum</button>
    </div>
  </div>

  <div class="card">
    <h2>Situation / Purpose</h2>
    <div class="full">
      <label>Describe what this letter is about</label>
      <textarea id="situation" rows="4" placeholder="e.g. I have 5 printers. 1 printer is not working and needs replacement. I want to request procurement of 1 new printer."></textarea>
    </div>
  </div>

  <div class="card">
    <h2>Office Details</h2>
    <div class="grid">
      <div><label>Unit / HQ</label><input id="unit" placeholder="Air HQ"></div>
      <div><label>Branch</label><input id="branch" placeholder="Ops Br"></div>
      <div><label>Directorate</label><input id="dte" placeholder="Dte CW&IT"></div>
      <div><label>Address</label><input id="address" placeholder="Dhaka Cantt"></div>
      <div><label>Telephone</label><input id="tel" placeholder="55060000 ext 3163"></div>
      <div><label>Email</label><input id="email" placeholder="xxx@baf.mil.bd"></div>
    </div>
  </div>

  <div class="card">
    <h2>Reference & Date</h2>
    <div class="grid">
      <div><label>File Reference Number</label><input id="fileRef" placeholder="00.03.2600.020.45.005.24.003/"></div>
      <div><label>Date</label><input id="date" placeholder="Jul 24"></div>
      <div><label>Classification</label>
        <select id="classification">
          <option value="RESTRICTED">RESTRICTED</option>
          <option value="CONFIDENTIAL">CONFIDENTIAL</option>
          <option value="SECRET">SECRET</option>
          <option value="TOP SECRET">TOP SECRET</option>
          <option value="UNCLASSIFIED">UNCLASSIFIED</option>
        </select>
      </div>
      <div><label>Priority</label>
        <select id="priority">
          <option value="">ROUTINE (no label)</option>
          <option value="IMMEDIATE">IMMEDIATE</option>
          <option value="URGENT">URGENT</option>
        </select>
      </div>
    </div>
  </div>

  <div class="card" id="section-lm-fields">
    <h2>Loose Minute Details</h2>
    <div class="grid">
      <div><label>LM Reference</label><input id="lmRef" placeholder="00.03.2600.020.45.004.24.003/"></div>
      <div><label>Extension Number</label><input id="ext" placeholder="3163"></div>
    </div>
  </div>

  <div class="card">
    <h2>References (Optional)</h2>
    <div class="full">
      <label>List any references (one per line)</label>
      <textarea id="refs" rows="3" placeholder="Air HQ ltr no 00.03.2600.020.45.008.22.001 dt 06 Dec 22"></textarea>
    </div>
  </div>

  <div class="card">
    <h2>Signing Authority</h2>
    <div class="grid">
      <div><label>Full Name (CAPS)</label><input id="sigName" placeholder="SAD WADI SAJID"></div>
      <div><label>Rank (exactly as required)</label><input id="sigRank" placeholder="Flt Lt"></div>
      <div><label>Appointment (exactly as required)</label><input id="sigAppt" placeholder="AD CW&IT"></div>
      <div><label>Signing For (if applicable)</label><input id="sigFor" placeholder="D CW&IT"></div>
    </div>
  </div>

  <div class="card" id="section-rl-fields">
    <h2>Distribution List</h2>
    <div class="grid">
      <div><label>External Action (one per line)</label><textarea id="extlAct" rows="3" placeholder="201 MU BAF"></textarea></div>
      <div><label>External Info (one per line)</label><textarea id="extlInfo" rows="3" placeholder="HQ BAF"></textarea></div>
      <div><label>Internal Action (one per line)</label><textarea id="intlAct" rows="3" placeholder="Dte Sup"></textarea></div>
      <div><label>Internal Info (one per line)</label><textarea id="intlInfo" rows="3" placeholder="SO to ACAS (O)"></textarea></div>
    </div>
  </div>

  <div class="card" id="section-to-fields">
    <h2>To / Info</h2>
    <div class="grid">
      <div><label>To (one per line)</label><textarea id="to" rows="3" placeholder="DMS (Air)"></textarea></div>
      <div><label>Info (one per line)</label><textarea id="info" rows="3" placeholder="SO to ACAS (O)"></textarea></div>
    </div>
  </div>

  <button class="run-btn" id="genBtn" onclick="generate()">▶ GENERATE LETTER</button>
  <div class="status" id="status"></div>
  <button class="dl-btn" id="dlBtn" onclick="download()">⬇ DOWNLOAD .DOCX</button>

</div>
<script>
let currentType = 'rl';
let lastFilename = '';

function setType(t, e) {
  currentType = t;
  document.querySelectorAll('.type-btn').forEach(b => b.classList.remove('active'));
  if (e && e.target) e.target.classList.add('active');
  document.getElementById('section-lm-fields').style.display = t === 'lm' ? 'block' : 'none';
  document.getElementById('section-rl-fields').style.display = t === 'rl' ? 'block' : 'none';
  document.getElementById('section-to-fields').style.display = t !== 'rl' ? 'block' : 'none';
}

setType('rl', null);
document.querySelector('.type-btn').classList.add('active');
document.getElementById('section-rl-fields').style.display = 'block';
document.getElementById('section-to-fields').style.display = 'none';

function val(id) { return document.getElementById(id)?.value?.trim() || ''; }
function lines(id) { return val(id).split('\n').map(s=>s.trim()).filter(Boolean); }

function showStatus(msg, type='info') {
  const el = document.getElementById('status');
  el.textContent = msg;
  el.className = 'status ' + type;
  el.style.display = 'block';
}

async function generate() {
  const btn = document.getElementById('genBtn');
  const dlBtn = document.getElementById('dlBtn');
  btn.disabled = true;
  dlBtn.style.display = 'none';
  showStatus('⏳ Generating letter with AI...', 'info');

  const data = {
    type:           currentType,
    situation:      val('situation'),
    unit:           val('unit'),
    branch:         val('branch'),
    dte:            val('dte'),
    address:        val('address'),
    tel:            val('tel'),
    email:          val('email'),
    fileRef:        val('fileRef'),
    date:           val('date'),
    classification: val('classification'),
    priority:       val('priority'),
    refs:           val('refs'),
    sigName:        val('sigName'),
    sigRank:        val('sigRank'),
    sigAppt:        val('sigAppt'),
    sigFor:         val('sigFor'),
    lmRef:          val('lmRef'),
    ext:            val('ext'),
    extlAct:        lines('extlAct').join('\n'),
    extlInfo:       lines('extlInfo').join('\n'),
    intlAct:        lines('intlAct').join('\n'),
    intlInfo:       lines('intlInfo').join('\n'),
    to:             lines('to').join('\n'),
    info:           lines('info').join('\n'),
  };

  try {
    const r = await fetch('/generate', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(data)
    });
    const res = await r.json();
    if (res.ok) {
      lastFilename = res.filename;
      showStatus('✅ Letter generated successfully!', 'ok');
      dlBtn.style.display = 'block';
    } else {
      showStatus('❌ Error: ' + res.error, 'err');
    }
  } catch(e) {
    showStatus('❌ ' + e.message, 'err');
  }
  btn.disabled = false;
}

function download() {
  if (lastFilename) window.location = '/download/' + lastFilename;
}
</script>
</body>
</html>"""

LEARNING_CENTER_PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>BAF Letter Learning Center</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600&display=swap');
  :root{--bg:#0b0f14;--surface:#111820;--border:#1e2d3d;--accent:#00bfff;--text:#cdd9e5;--muted:#4a6070;--success:#00e5a0;--error:#ff4d4d;}
  *{box-sizing:border-box;margin:0;padding:0}
  body{background:var(--bg);color:var(--text);font-family:'Inter',sans-serif;font-size:14px;min-height:100vh}
  header{background:var(--surface);border-bottom:1px solid var(--border);padding:14px 28px;display:flex;align-items:center;gap:16px}
  .badge{background:#00e5a0;color:#000;font-weight:700;font-size:11px;letter-spacing:2px;padding:4px 10px;border-radius:2px}
  header h1{font-size:15px;font-weight:600;letter-spacing:1px}
  header a{margin-left:auto;color:var(--accent);font-size:12px;text-decoration:none}
  .wrap{max-width:900px;margin:0 auto;padding:28px 20px}
  .card{background:var(--surface);border:1px solid var(--border);border-radius:6px;padding:24px;margin-bottom:20px}
  .card h2{font-size:11px;letter-spacing:2px;color:var(--muted);text-transform:uppercase;margin-bottom:16px}
  label{display:block;font-size:11px;color:var(--muted);letter-spacing:1px;margin-bottom:5px;text-transform:uppercase}
  textarea{width:100%;background:var(--bg);border:1px solid var(--border);border-radius:4px;color:var(--text);font-family:'Inter',sans-serif;font-size:13px;padding:9px 12px;outline:none;resize:vertical;min-height:140px;transition:border-color .2s}
  textarea:focus{border-color:var(--accent)}
  input{width:100%;background:var(--bg);border:1px solid var(--border);border-radius:4px;color:var(--text);font-family:'Inter',sans-serif;font-size:13px;padding:9px 12px;outline:none;transition:border-color .2s}
  .btn{border:none;border-radius:4px;font-weight:700;font-size:13px;padding:12px 20px;cursor:pointer;transition:all .2s}
  .btn-primary{background:var(--accent);color:#000;letter-spacing:1px}
  .btn-primary:hover{background:#33ccff}
  .btn-accept{background:var(--success);color:#000}
  .btn-reject{background:transparent;border:1px solid var(--error);color:var(--error)}
  .btn-reject:hover{background:var(--error);color:#000}
  .diff-box{background:var(--bg);border:1px solid var(--border);border-radius:4px;padding:14px;font-size:13px;line-height:1.7;white-space:pre-wrap;font-family:monospace}
  .diff-added{color:var(--success)}
  .diff-removed{color:var(--error);text-decoration:line-through}
  .change-item{background:var(--bg);border:1px solid var(--border);border-radius:4px;padding:12px 16px;margin-bottom:10px;display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap}
  .change-desc{flex:1;font-size:13px}
  .change-actions{display:flex;gap:8px;flex-shrink:0}
  .status-msg{padding:10px 14px;border-radius:4px;font-size:13px;margin-top:10px;display:none}
  .status-msg.ok{background:rgba(0,229,160,.1);border:1px solid var(--success);color:var(--success);display:block}
  .status-msg.err{background:rgba(255,77,77,.1);border:1px solid var(--error);color:var(--error);display:block}
  .grid2{display:grid;grid-template-columns:1fr 1fr;gap:14px}
</style>
</head>
<body>
<header>
  <div class="badge">BAF</div>
  <h1>LETTER LEARNING CENTER</h1>
  <a href="/">&#8592; Back to Generator</a>
</header>
<div class="wrap">

  <div class="card">
    <h2>Step 1 — Paste Letters to Compare</h2>
    <div class="grid2">
      <div>
        <label>Original AI-Generated Letter</label>
        <textarea id="origText" placeholder="Paste the original AI letter text here..."></textarea>
      </div>
      <div>
        <label>Your Final Edited Letter</label>
        <textarea id="finalText" placeholder="Paste your corrected/final version here..."></textarea>
      </div>
    </div>
    <div style="margin-top:12px">
      <label>Letter ID / Reference (optional)</label>
      <input id="letterId" placeholder="e.g. 00.03.2600.020.45.005.24.003">
    </div>
    <button class="btn btn-primary" style="margin-top:14px;width:100%" onclick="compare()">&#9658; COMPARE &amp; DETECT CHANGES</button>
    <div class="status-msg" id="cmpStatus"></div>
  </div>

  <div class="card" id="resultsCard" style="display:none">
    <h2>Step 2 — Detected Changes</h2>
    <div id="diffOutput" class="diff-box" style="margin-bottom:16px"></div>
    <div id="changesContainer"></div>
    <div class="status-msg" id="learnStatus"></div>
  </div>

</div>
<script>
function showMsg(id, msg, type) {
  const el = document.getElementById(id);
  el.textContent = msg;
  el.className = 'status-msg ' + type;
}

async function compare() {
  const orig = document.getElementById('origText').value.trim();
  const final = document.getElementById('finalText').value.trim();
  const letterId = document.getElementById('letterId').value.trim() || 'draft';
  if (!orig || !final) { showMsg('cmpStatus','Please paste both letters.','err'); return; }

  const r = await fetch('/learn', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({ letter_id: letterId, original_json: {body:[orig]}, final_json: {body:[final]} })
  });
  const res = await r.json();
  if (!res.ok) { showMsg('cmpStatus', 'Error: ' + res.error, 'err'); return; }

  const comp = res.comparison;
  document.getElementById('resultsCard').style.display = 'block';

  // Show raw diff
  const diffEl = document.getElementById('diffOutput');
  let diffHtml = '';
  (comp.raw_diff || []).forEach(line => {
    if (line.startsWith('+ ')) diffHtml += `<span class="diff-added">+ ${escHtml(line.slice(2))}</span>\n`;
    else if (line.startsWith('- ')) diffHtml += `<span class="diff-removed">- ${escHtml(line.slice(2))}</span>\n`;
  });
  diffEl.innerHTML = diffHtml || '<em style="color:var(--muted)">No line-level differences detected.</em>';

  // Show detected style changes
  const container = document.getElementById('changesContainer');
  container.innerHTML = '';
  const changes = comp.changes || [];
  if (!changes.length) {
    container.innerHTML = '<p style="color:var(--muted);font-size:13px">No style preferences detected from this edit.</p>';
  } else {
    changes.forEach((ch, idx) => {
      const div = document.createElement('div');
      div.className = 'change-item';
      div.innerHTML = `
        <div class="change-desc"><strong>${escHtml(ch.key)}</strong> &rarr; <em>${escHtml(ch.detected)}</em><br><span style="color:var(--muted)">${escHtml(ch.desc)}</span></div>
        <div class="change-actions">
          <button class="btn btn-accept" onclick="acceptChange(${idx},'${escHtml(ch.key)}','${escHtml(ch.detected)}')">&#10003; Accept as Preference</button>
          <button class="btn btn-reject" onclick="rejectChange(${idx})">&#10007; Reject</button>
        </div>`;
      container.appendChild(div);
    });
  }
}

async function acceptChange(idx, key, value) {
  const r = await fetch('/accept-preference', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({key, value})
  });
  const res = await r.json();
  if (res.ok) {
    showMsg('learnStatus', `Preference "${key}" updated (${res.status}).`, 'ok');
    document.querySelectorAll('.change-item')[idx].style.opacity = '0.4';
  } else {
    showMsg('learnStatus', 'Error: ' + res.error, 'err');
  }
}
function rejectChange(idx) {
  document.querySelectorAll('.change-item')[idx].style.opacity = '0.4';
  showMsg('learnStatus', 'Change rejected — not saved.', 'ok');
}
function escHtml(s) { return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }
</script>
</body>
</html>"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        print(f"[{time.strftime('%H:%M:%S')}]", format % args)

    def do_GET(self):
        if self.path == '/':
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(HTML_PAGE.encode())
        elif self.path == '/learning-center':
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(LEARNING_CENTER_PAGE.encode())
        elif self.path.startswith('/download/'):
            fname = self.path.split('/download/')[-1]
            fpath = os.path.join(tempfile.gettempdir(), fname)
            if os.path.exists(fpath):
                self.send_response(200)
                self.send_header('Content-Type', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document')
                self.send_header('Content-Disposition', f'attachment; filename="{fname}"')
                self.end_headers()
                with open(fpath, 'rb') as f:
                    self.wfile.write(f.read())
            else:
                self.send_response(404)
                self.end_headers()
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        if self.path == '/generate':
            length = int(self.headers['Content-Length'])
            body   = json.loads(self.rfile.read(length))
            try:
                print(f"[{time.strftime('%H:%M:%S')}] Generating {body.get('type','rl').upper()} — {body.get('classification','')} {body.get('priority','')}")
                letter_json = generate_letter_json(body['type'], body)
                fname  = f"BAF_letter_{body['type']}_{int(time.time())}.docx"
                fpath  = os.path.join(tempfile.gettempdir(), fname)
                run_node_generator(letter_json, fpath)
                resp = {'ok': True, 'filename': fname}
            except Exception as e:
                import traceback; traceback.print_exc()
                resp = {'ok': False, 'error': str(e)}
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(resp).encode())
        elif self.path == '/accept-preference':
            length = int(self.headers['Content-Length'])
            body   = json.loads(self.rfile.read(length))
            try:
                from style_manager import update_preference
                key = body.get('key', '')
                value = body.get('value', '')
                result = update_preference(key, value)
                resp = {'ok': True, 'status': result['status'], 'edit_count': result['edit_count']}
            except Exception as e:
                import traceback; traceback.print_exc()
                resp = {'ok': False, 'error': str(e)}
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(resp).encode())
            length = int(self.headers['Content-Length'])
            body   = json.loads(self.rfile.read(length))
            try:
                letter_id = body.get('letter_id', 'draft')
                orig_json = body.get('original_json', {})
                final_json = body.get('final_json', {})
                
                comp = log_learning_event(letter_id, orig_json, final_json, approved=True)
                resp = {'ok': True, 'comparison': comp}
            except Exception as e:
                import traceback; traceback.print_exc()
                resp = {'ok': False, 'error': str(e)}
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(resp).encode())


if __name__ == '__main__':
    # Ensure all directories and golden tests exist on startup
    init_dataset_structure()
    create_sample_golden_tests()

    print("=" * 55)
    print("  BAF Letter Generator Server  v3")
    print("=" * 55)
    print(f"  Letter Generator: http://localhost:{PORT}")
    print(f"  Learning Center:  http://localhost:{PORT}/learning-center")
    print(f"  Network: http://192.168.0.167:{PORT}")
    print(f"  Share Network URL with your team")
    print(f"\n  Press Ctrl+C to stop\n")
    HTTPServer(('0.0.0.0', PORT), Handler).serve_forever()