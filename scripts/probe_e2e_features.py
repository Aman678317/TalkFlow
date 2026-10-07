import urllib.request
import json
import traceback

BASE = "http://localhost:5173"

def request(path, method="GET", data=None, token=None):
    url = f"{BASE}{path}"
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    body = json.dumps(data).encode("utf-8") if data is not None else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            content = resp.read().decode("utf-8")
            try:
                return resp.status, json.loads(content)
            except Exception:
                return resp.status, content
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8")
        try:
            return e.code, json.loads(err_body)
        except Exception:
            return e.code, err_body
    except Exception as e:
        return 0, str(e)

def main():
    print("=== PROBING ALL ENDPOINTS VIA VITE PROXY (http://localhost:5173) ===")
    
    # 0. Health check
    st, res = request("/health")
    print(f"Health check [/health]: status={st}, res={res}")
    
    # 1. Login
    st, res = request("/api/v1/auth/login", method="POST", data={"email": "demo@globaltalk.local", "password": "demo1234"})
    print(f"Auth login: status={st}")
    if st != 200:
        print("Login failed! Response:", res)
        return
    token = res.get("tokens", {}).get("access_token")
    print(f"Got access token: {token[:15]}...")
    
    # 2. Text Translation (/translate)
    st, res = request("/api/v1/translate", method="POST", token=token, data={
        "text": "Hello, how are you today?",
        "source_language": "en",
        "target_language": "es"
    })
    print(f"Text Translation [/api/v1/translate]: status={st}, res={res}")
    
    # 3. AI Writing Assistant (/write)
    st, res = request("/api/v1/write/rephrase", method="POST", token=token, data={
        "text": "Hey whats up we should totally do this thing",
        "style": "professional"
    })
    print(f"Writing Rephrase [/api/v1/write/rephrase]: status={st}, res={res}")
    
    st, res = request("/api/v1/write/correct", method="POST", token=token, data={
        "text": "He dont have no time for this."
    })
    print(f"Writing Correct [/api/v1/write/correct]: status={st}, res={res}")
    
    # 4. Meetings (/meetings)
    st, res = request("/api/v1/meetings", method="POST", token=token, data={
        "title": "Global multilingual standup"
    })
    print(f"Create Meeting [/api/v1/meetings]: status={st}, res={res}")
    meeting_id = res.get("id") if isinstance(res, dict) else None
    
    if meeting_id:
        st, res = request(f"/api/v1/meetings/{meeting_id}", method="GET", token=token)
        print(f"Get Meeting Details: status={st}, id={meeting_id}")
        
        # Voice session token
        st, res = request(f"/api/v1/voice/session?meeting_id={meeting_id}", method="POST", token=token, data={})
        print(f"Voice Session Token [/api/v1/voice/session]: status={st}, res={res}")
    
    # 5. Glossaries (/glossaries)
    st, res = request("/api/v1/glossaries", method="GET", token=token)
    print(f"List Glossaries [/api/v1/glossaries]: status={st}, count={len(res) if isinstance(res, list) else res}")
    
    # Create glossary term
    st, res = request("/api/v1/glossaries", method="POST", token=token, data={
        "source_term": "Pipeline",
        "target_term": "Tubería",
        "source_language": "en",
        "target_language": "es",
        "domain": "Engineering"
    })
    print(f"Create Glossary [/api/v1/glossaries]: status={st}, res={res}")
    
    # 6. Usage Quotas (/usage)
    st, res = request("/api/v1/usage", method="GET", token=token)
    print(f"Usage & Quotas [/api/v1/usage]: status={st}, res={res}")
    
    # 7. Document Translation (/documents)
    # Check document endpoints
    st, res = request("/api/v1/documents", method="GET", token=token)
    print(f"List Documents [/api/v1/documents]: status={st}, res={res}")

    print("=== END PROBE ===")

if __name__ == "__main__":
    main()
