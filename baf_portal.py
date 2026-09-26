"""
BAF Knowledge Portal
=====================
Proxies requests to AnythingLLM and serves a clean web UI
to all users on the local network.

Run:  py baf_portal.py
Open: http://192.168.0.218:8080  (from any PC on your LAN)

Config: edit the ANYTHINGLLM_* values below if needed.
"""

import json, time, re, os
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.request import urlopen, Request
from urllib.error import URLError
import urllib.parse

# ── CONFIG ──────────────────────────────────────────────────────────
ANYTHINGLLM_URL = os.environ.get("ANYTHINGLLM_URL", "http://127.0.0.1:3001")
API_KEY         = os.environ.get("ANYTHINGLLM_API_KEY", "")
PORT            = int(os.environ.get("PORT", "8080"))
HOST            = "0.0.0.0"   # listen on all interfaces = accessible from LAN
# ────────────────────────────────────────────────────────────────────

HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type":  "application/json",
}

def anythingllm_get(path):
    req = Request(ANYTHINGLLM_URL + path, headers=HEADERS)
    try:
        with urlopen(req, timeout=10) as r:
            return json.loads(r.read())
    except Exception as e:
        return {"error": str(e)}

def anythingllm_post(path, data):
    body = json.dumps(data).encode()
    req  = Request(ANYTHINGLLM_URL + path, data=body, headers=HEADERS, method="POST")
    try:
        with urlopen(req, timeout=120) as r:
            return json.loads(r.read())
    except Exception as e:
        return {"error": str(e)}


HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>BAF Knowledge Portal</title>
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600&family=Share+Tech+Mono&display=swap');
:root{
  --bg:#0b0f14;--surface:#111820;--surface2:#162030;--border:#1e2d3d;
  --accent:#00bfff;--accent2:#005f7f;--text:#cdd9e5;--muted:#4a6070;
  --success:#00e5a0;--error:#ff4d4d;--mono:'Share Tech Mono',monospace;
}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--text);font-family:'Inter',sans-serif;font-size:14px;height:100vh;display:flex;flex-direction:column}
/* ── HEADER ── */
header{background:var(--surface);border-bottom:1px solid var(--border);padding:12px 24px;display:flex;align-items:center;gap:14px;flex-shrink:0}
.badge{background:var(--accent);color:#000;font-family:var(--mono);font-size:11px;font-weight:700;letter-spacing:2px;padding:4px 10px;border-radius:2px}
header h1{font-size:14px;font-weight:600;letter-spacing:1px}
.status{margin-left:auto;font-family:var(--mono);font-size:11px;color:var(--muted);display:flex;align-items:center;gap:6px}
.dot{width:7px;height:7px;border-radius:50%;background:var(--muted)}
.dot.on{background:var(--success);box-shadow:0 0 5px var(--success)}
/* ── LAYOUT ── */
.app{display:flex;flex:1;overflow:hidden}
/* ── SIDEBAR ── */
.sidebar{width:220px;background:var(--surface);border-right:1px solid var(--border);display:flex;flex-direction:column;padding:16px 12px;gap:6px;flex-shrink:0}
.sidebar-label{font-family:var(--mono);font-size:9px;letter-spacing:2px;color:var(--muted);text-transform:uppercase;margin:10px 0 4px 6px}
.ws-btn{background:transparent;border:1px solid transparent;border-radius:4px;color:var(--muted);font-family:'Inter',sans-serif;font-size:13px;padding:9px 12px;cursor:pointer;text-align:left;width:100%;transition:all .2s;display:flex;align-items:center;gap:8px}
.ws-btn:hover{background:var(--surface2);border-color:var(--border);color:var(--text)}
.ws-btn.active{background:var(--accent2);border-color:var(--accent);color:var(--accent)}
.ws-icon{font-size:15px}
/* ── MAIN ── */
.main{flex:1;display:flex;flex-direction:column;overflow:hidden}
.chat-header{padding:12px 20px;border-bottom:1px solid var(--border);background:var(--surface);font-size:12px;color:var(--muted);display:flex;align-items:center;gap:8px}
.chat-header strong{color:var(--text)}
.messages{flex:1;overflow-y:auto;padding:20px;display:flex;flex-direction:column;gap:14px}
.msg{max-width:80%;padding:12px 16px;border-radius:6px;font-size:13px;line-height:1.6}
.msg.user{background:var(--accent2);border:1px solid var(--accent);align-self:flex-end;color:var(--text)}
.msg.ai{background:var(--surface);border:1px solid var(--border);align-self:flex-start;white-space:pre-wrap}
.msg.ai .src{font-family:var(--mono);font-size:10px;color:var(--muted);margin-top:8px;padding-top:8px;border-top:1px solid var(--border)}
.msg.thinking{color:var(--muted);font-style:italic;font-size:12px;align-self:flex-start}
.msg.err{background:rgba(255,77,77,.1);border-color:var(--error);color:var(--error);align-self:flex-start}
/* ── INPUT ── */
.input-area{padding:14px 20px;border-top:1px solid var(--border);background:var(--surface);display:flex;gap:10px;align-items:flex-end}
textarea{flex:1;background:var(--bg);border:1px solid var(--border);border-radius:4px;color:var(--text);font-family:'Inter',sans-serif;font-size:13px;padding:10px 12px;outline:none;resize:none;max-height:120px;min-height:42px;transition:border-color .2s;line-height:1.5}
textarea:focus{border-color:var(--accent)}
.send-btn{background:var(--accent);color:#000;border:none;border-radius:4px;font-weight:700;font-size:12px;letter-spacing:1px;padding:10px 18px;cursor:pointer;flex-shrink:0;transition:background .2s;height:42px}
.send-btn:hover{background:#33ccff}
.send-btn:disabled{background:var(--muted);cursor:not-allowed}
/* ── WELCOME ── */
.welcome{flex:1;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:12px;color:var(--muted);text-align:center;padding:40px}
.welcome h2{font-size:18px;color:var(--text);font-weight:500}
.welcome p{font-size:13px;max-width:400px;line-height:1.6}
.workspace-cards{display:grid;grid-template-columns:repeat(2,1fr);gap:10px;margin-top:16px;width:100%;max-width:500px}
.ws-card{background:var(--surface);border:1px solid var(--border);border-radius:6px;padding:16px;cursor:pointer;transition:all .2s;text-align:left}
.ws-card:hover{border-color:var(--accent);background:var(--surface2)}
.ws-card .icon{font-size:22px;margin-bottom:6px}
.ws-card .name{font-size:13px;font-weight:500;color:var(--text)}
.ws-card .desc{font-size:11px;color:var(--muted);margin-top:2px}
/* ── SCROLLBAR ── */
::-webkit-scrollbar{width:4px}
::-webkit-scrollbar-track{background:transparent}
::-webkit-scrollbar-thumb{background:var(--border);border-radius:2px}
</style>
</head>
<body>
<header>
  <div class="badge">BAF</div>
  <h1>KNOWLEDGE PORTAL</h1>
  <div class="status"><span class="dot" id="dot"></span><span id="statusTxt">Connecting...</span></div>
</header>
<div class="app">
  <div class="sidebar">
    <div class="sidebar-label">Workspaces</div>
    <div id="wsList">
      <div style="color:var(--muted);font-size:12px;padding:8px">Loading...</div>
    </div>
  </div>
  <div class="main">
    <div id="welcomeScreen" class="welcome">
      <h2>Welcome to BAF Knowledge Portal</h2>
      <p>Select a workspace from the left to start searching policies, regulations, JSSDM documents, and more.</p>
      <div class="workspace-cards" id="wsCards"></div>
    </div>
    <div id="chatScreen" style="display:none;flex:1;flex-direction:column;overflow:hidden">
      <div class="chat-header">
        <span id="chatIcon">📄</span>
        <strong id="chatTitle">Workspace</strong>
        <span>— ask anything from the documents</span>
      </div>
      <div class="messages" id="messages"></div>
      <div class="input-area">
        <textarea id="input" placeholder="Ask a question or search for a policy..." rows="1" onkeydown="handleKey(event)" oninput="autoResize(this)"></textarea>
        <button class="send-btn" id="sendBtn" onclick="sendMessage()">SEND</button>
      </div>
    </div>
  </div>
</div>
<script>
let currentWorkspace = null;
let workspaces = [];

const ICONS = {
  'policies': '📋', 'policy': '📋', 'laws': '📋',
  'jssdm': '📖', 'letters': '✉️', 'letter': '✉️',
  'ebooks': '📚', 'book': '📚', 'vision': '🖼️',
  'images': '🖼️', 'text': '💬'
};

function getIcon(name) {
  const n = name.toLowerCase();
  for (const [k, v] of Object.entries(ICONS)) {
    if (n.includes(k)) return v;
  }
  return '📄';
}

async function init() {
  try {
    const r = await fetch('/api/workspaces');
    const data = await r.json();
    if (data.error) throw new Error(data.error);
    workspaces = data.workspaces || [];
    renderWorkspaces();
    document.getElementById('dot').classList.add('on');
    document.getElementById('statusTxt').textContent = 'Connected';
  } catch(e) {
    document.getElementById('statusTxt').textContent = 'AnythingLLM offline';
    document.getElementById('wsList').innerHTML = '<div style="color:var(--error);font-size:11px;padding:8px">Could not connect</div>';
  }
}

function renderWorkspaces() {
  const list = document.getElementById('wsList');
  const cards = document.getElementById('wsCards');
  list.innerHTML = '';
  cards.innerHTML = '';

  workspaces.forEach(ws => {
    const icon = getIcon(ws.name);
    // Sidebar button
    const btn = document.createElement('button');
    btn.className = 'ws-btn';
    btn.innerHTML = `<span class="ws-icon">${icon}</span>${ws.name}`;
    btn.onclick = () => selectWorkspace(ws, icon);
    list.appendChild(btn);
    // Welcome card
    const card = document.createElement('div');
    card.className = 'ws-card';
    card.innerHTML = `<div class="icon">${icon}</div><div class="name">${ws.name}</div><div class="desc">Click to chat</div>`;
    card.onclick = () => selectWorkspace(ws, icon);
    cards.appendChild(card);
  });
}

function selectWorkspace(ws, icon) {
  currentWorkspace = ws;
  document.getElementById('welcomeScreen').style.display = 'none';
  const cs = document.getElementById('chatScreen');
  cs.style.display = 'flex';
  cs.style.flexDirection = 'column';
  document.getElementById('chatTitle').textContent = ws.name;
  document.getElementById('chatIcon').textContent = icon || '📄';
  document.getElementById('messages').innerHTML = '';
  document.querySelectorAll('.ws-btn').forEach(b => b.classList.remove('active'));
  document.querySelectorAll('.ws-btn').forEach(b => {
    if (b.textContent.trim().includes(ws.name)) b.classList.add('active');
  });
  document.getElementById('input').focus();
}

function autoResize(el) {
  el.style.height = 'auto';
  el.style.height = Math.min(el.scrollHeight, 120) + 'px';
}

function handleKey(e) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    sendMessage();
  }
}

function addMsg(text, type, sources) {
  const div = document.createElement('div');
  div.className = 'msg ' + type;
  div.textContent = text;
  if (sources && sources.length) {
    const src = document.createElement('div');
    src.className = 'src';
    src.textContent = '📎 Sources: ' + sources.map(s => s.title || s.id).join(', ');
    div.appendChild(src);
  }
  document.getElementById('messages').appendChild(div);
  div.scrollIntoView({ behavior: 'smooth' });
  return div;
}

async function sendMessage() {
  if (!currentWorkspace) return;
  const input = document.getElementById('input');
  const msg = input.value.trim();
  if (!msg) return;

  input.value = '';
  input.style.height = 'auto';
  document.getElementById('sendBtn').disabled = true;

  addMsg(msg, 'user');
  const thinking = addMsg('Searching documents...', 'thinking');

  try {
    const r = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ workspace: currentWorkspace.slug, message: msg })
    });
    const data = await r.json();
    thinking.remove();
    if (data.error) {
      addMsg('Error: ' + data.error, 'err');
    } else {
      const text = data.textResponse || data.response || 'No response';
      const sources = data.sources || [];
      addMsg(text, 'ai', sources);
    }
  } catch(e) {
    thinking.remove();
    addMsg('Connection error: ' + e.message, 'err');
  }

  document.getElementById('sendBtn').disabled = false;
  document.getElementById('input').focus();
}

init();
</script>
</body>
</html>"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        print(f"[{time.strftime('%H:%M:%S')}] {fmt % args}")

    def send_json(self, data, status=200):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == '/':
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(HTML.encode())

        elif self.path == '/api/workspaces':
            data = anythingllm_get('/api/v1/workspaces')
            self.send_json(data)

        elif self.path == '/api/ping':
            self.send_json({'ok': True})

        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        if self.path == '/api/chat':
            length = int(self.headers['Content-Length'])
            body   = json.loads(self.rfile.read(length))
            slug   = body.get('workspace', '')
            msg    = body.get('message', '')

            result = anythingllm_post(
                f'/api/v1/workspace/{slug}/chat',
                {"message": msg, "mode": "chat"}
            )
            self.send_json(result)
        else:
            self.send_response(404)
            self.end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()


if __name__ == '__main__':
    print("=" * 55)
    print("  BAF Knowledge Portal")
    print("=" * 55)
    print(f"  Local:   http://localhost:{PORT}")
    print(f"  Network: http://192.168.0.218:{PORT}")
    print(f"  Share the Network URL with your team")
    print(f"\n  Press Ctrl+C to stop\n")
    HTTPServer((HOST, PORT), Handler).serve_forever()
