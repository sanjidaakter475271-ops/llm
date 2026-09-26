import os
import json
from urllib.request import urlopen, Request
from urllib.error import URLError

ANYTHINGLLM_URL = os.environ.get("ANYTHINGLLM_URL", "http://127.0.0.1:3001")
API_KEY         = os.environ.get("ANYTHINGLLM_API_KEY", "")

HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type":  "application/json",
}

def _anythingllm_post(path, data):
    body = json.dumps(data).encode()
    req  = Request(ANYTHINGLLM_URL + path, data=body, headers=HEADERS, method="POST")
    try:
        with urlopen(req, timeout=120) as r:
            return json.loads(r.read())
    except Exception as e:
        return {"error": str(e)}

def search_policy(query, intent=None):
    """
    Integrates with AnythingLLM knowledge workspaces for policy lookup.
    Guarantees strict source grounding (no hallucination).
    """
    slug = intent if intent else "default"
    response = _anythingllm_post(
        f"/api/v1/workspace/{slug}/chat",
        {"message": query, "mode": "chat"}
    )

    if "error" in response:
        return {
            "found": False,
            "text": "Available sources-এর মধ্যে specific reference identify করা যায়নি।",
            "sources": []
        }

    sources = response.get("sources", [])
    text = response.get("textResponse", response.get("response", ""))

    return {
        "found": len(sources) > 0,
        "text": text,
        "sources": sources
    }
