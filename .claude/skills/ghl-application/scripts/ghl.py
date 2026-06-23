#!/usr/bin/env python3
"""Self-contained GHL client for workflow-automation work (current auth model).

Two auth worlds (do not mix them):
  * WORKFLOW API   backend.leadconnectorhq.com/workflow   -> Authorization: Bearer <user JWT>
                   + channel: APP + origin: <workflows app origin>     (token: ~/.ghl-token)
  * SERVICES API   services.leadconnectorhq.com/*         -> Authorization: Bearer <pit-...>
                   + Version header                                    (token: ~/.ghl-pit)

CLI:
  ghl.py scan "<pasted credential>"               # detect+store Bearer and/or pit- token
  ghl.py nodes <loc> <wf>
  ghl.py audit-emails <loc> <wf>                  # §6a content & timing checks
  ghl.py set-event-date <loc> <wf> <ISO8601>
  ghl.py cv-list <loc>
  ghl.py cv-create <loc> <name> <value>
  ghl.py email-create <loc> <title> <htmlfile>    # prints template_id
  ghl.py point-template <loc> <wf> <nodeId> <templateId> [subject] [preheader]
  ghl.py templates <loc>                          # list email-builder templates
  ghl.py template-html <loc> <templateId>         # dump a template's HTML (styling base)
  ghl.py add-email-after <loc> <wf> <afterNodeId> <title> <htmlfile> <waitMinutes> [subject] [preheader]
  ghl.py trigger-link <loc> <name> <redirectUrl>
"""
import sys, os, re, json, base64, time, uuid, urllib.request, urllib.error
from datetime import datetime, timedelta

WF_BASE  = "https://backend.leadconnectorhq.com/workflow"
SVC_BASE = "https://services.leadconnectorhq.com"
ORIGIN   = "https://client-app-automation-workflows.leadconnectorhq.com"
TOKEN_FILE = os.path.expanduser("~/.ghl-token")
PIT_FILE   = os.path.expanduser("~/.ghl-pit")
UA = "Mozilla/5.0 (ghl-application-skill)"   # Cloudflare 403s default urllib UA

# §6a time-of-day -> canonical in-window minute-of-day (R1). night == evening.
TIME_OF_DAY = {"morning": 9*60, "afternoon": 15*60, "evening": 21*60, "night": 21*60}
# R1 approved send windows (minute-of-day, inclusive): 08-09, 15-16, 20-21.
WINDOWS = ((8*60, 9*60), (15*60, 16*60), (20*60, 21*60))
MIN_GAP_MIN = 4*60   # R2: >= 4h between same-day emails
PRE_FAR_MIN = 12*60  # R6 phase boundary: >=12h before webinar -> Add-to-Calendar

def _tok(path, label):
    if not os.path.exists(path):
        sys.exit(f"missing {label} token at {path} — run `ghl.py scan \"<paste>\"` first")
    return open(path).read().strip()

def wf_token():  return _tok(TOKEN_FILE, "workflow")
def pit_token(): return _tok(PIT_FILE, "services/PIT")

def _req(method, url, headers, body=None):
    headers = {**headers, "User-Agent": UA}
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(r) as resp:
            return resp.status, resp.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()

# ---------- token scan ----------
def _b64url(seg): return base64.urlsafe_b64decode(seg + "=" * (-len(seg) % 4))
def _decode_jwt(tok):
    try:    return json.loads(_b64url(tok.split(".")[1]))
    except Exception: return None

def cmd_scan(*text):
    raw = " ".join(text).strip()
    jwt = re.search(r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+", raw)
    pit = re.search(r"pit-[A-Za-z0-9-]+", raw)
    found = False
    if jwt:
        tok = jwt.group(0); claims = _decode_jwt(tok) or {}
        exp = claims.get("exp"); now = time.time()
        if claims.get("authClass") == "User":
            open(TOKEN_FILE, "w").write(tok); os.chmod(TOKEN_FILE, 0o600)
            print(f"[workflow] stored Authorization: Bearer token -> {TOKEN_FILE}")
            if exp:
                mins = (exp - now) / 60
                print(f"           {'VALID' if exp>now else 'EXPIRED'} "
                      f"({abs(mins):.0f} min {'left' if exp>now else 'ago'})")
            found = True
        else:
            print("[warn] JWT found but authClass != 'User' (legacy token-id). Not stored.")
    if pit:
        open(PIT_FILE, "w").write(pit.group(0)); os.chmod(PIT_FILE, 0o600)
        print(f"[services] stored Private Integration token -> {PIT_FILE}")
        found = True
    if not found:
        sys.exit("[error] No usable credential found. Paste 'Authorization: Bearer eyJ...' "
                 "and/or 'pit-...'.")

# ---------- workflow API ----------
def wf_headers(ct=False):
    h = {"Authorization": f"Bearer {wf_token()}", "channel": "APP", "origin": ORIGIN}
    if ct: h["Content-Type"] = "application/json"
    return h

def get_workflow(loc, wf):
    code, body = _req("GET", f"{WF_BASE}/{loc}/{wf}", wf_headers())
    if code == 401: sys.exit("401 — workflow token expired/invalid (or truncated). Re-scan a fresh Bearer token.")
    if code != 200: sys.exit(f"GET workflow failed {code}: {body[:300]}")
    return json.loads(body)

def put_workflow(loc, wf, d):
    code, body = _req("PUT", f"{WF_BASE}/{loc}/{wf}", wf_headers(ct=True), d)
    if code == 422: return "422"
    return str(code) if code in (200, 201) else f"FAIL {code}: {body[:300]}"

def modify_and_put(loc, wf, fn):
    """fn(d) mutates the workflow dict in place. Handles one 422 retry."""
    d = get_workflow(loc, wf); fn(d)
    res = put_workflow(loc, wf, d)
    if res == "422":
        d = get_workflow(loc, wf); fn(d)
        res = put_workflow(loc, wf, d)
    return res

# ---------- services API (PIT) ----------
def svc_headers(version="2021-07-28", ct=False):
    h = {"Authorization": f"Bearer {pit_token()}", "Version": version}
    if ct: h["Content-Type"] = "application/json"
    return h

# ---------- CLI commands ----------
def cmd_nodes(loc, wf):
    d = get_workflow(loc, wf)
    print(f"version {d.get('version')} | status {d.get('status')}")
    for n in d["workflowData"]["templates"]:
        print(f"  {n.get('order'):>3} | {n.get('type'):22} | {n.get('name')} | id={n.get('id')}")

def _wait_offset(node):
    """Signed offset in minutes from the webinar start (before = negative)."""
    a = node.get("attributes", {}) or {}
    asa = a.get("appointmentStartAfter") or {}
    try:    val = int(asa.get("value", 0) or 0)
    except (TypeError, ValueError): val = 0
    return -val if asa.get("when") == "before" else val

def _phase(off):
    if off <= -PRE_FAR_MIN: return "PRE-far"
    if off < 0:             return "PRE-near"
    return "POST"

def _in_window(mod):
    return any(lo <= mod <= hi for lo, hi in WINDOWS)

def _event_start(d):
    n = next((x for x in d["workflowData"]["templates"]
              if x.get("type") == "event_start_date"), None)
    v = ((n or {}).get("attributes") or {}).get("value") if n else None
    if not v: return None
    try:    return datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except ValueError: return None

def _cta(html):
    """Heuristic: (has_button, looks_like_calendar, looks_like_zoom)."""
    low = html.lower()
    has_btn = bool(re.search(r"<a\b[^>]*href", low))
    cal = any(k in low for k in ("add to calendar", "add-to-calendar", "addtocalendar",
              "add_to_calendar", ".ics", "calendar.google", "outlook.office", "/calendar",
              "calendar_link"))   # also match custom-value slugs e.g. {{custom_values.webinar_calendar_link}}
    zoom = any(k in low for k in ("zoom.us", "zoom_link", "webinar_zoom", "join the webinar",
              "join webinar", "join now", "join live", "join the room", "webinar_link"))
    return has_btn, cal, zoom

def _content_time_flags(low, off, send):
    """R8 — heuristic checks that body wording matches send time / phase."""
    out = []
    # (a) time-of-day greeting vs the send window
    if send is not None:
        mod = send.hour * 60 + send.minute
        win = ("morning" if 5*60 <= mod < 12*60 else "afternoon" if 12*60 <= mod < 17*60
               else "evening" if 17*60 <= mod < 22*60 else "night")
        greet = None
        if re.search(r"good\s+morning|this\s+morning", low):        greet = "morning"
        elif re.search(r"good\s+afternoon|this\s+afternoon", low):  greet = "afternoon"
        elif re.search(r"good\s+evening|this\s+evening|tonight", low): greet = "evening"
        if greet and greet != win and not (greet == "evening" and win == "night"):
            out.append(f"R8 body says '{greet}' but it sends in the {win} ({send.strftime('%H:%M')})")
    # (b) stated countdown vs actual offset (PRE emails only)
    if off < 0:
        actual = abs(off)
        for m in re.finditer(r"(\d{1,3})\s*(days?|hours?|hrs?|minutes?|mins?)\b", low):
            ctx = low[max(0, m.start()-45):m.end()+45]
            if not re.search(r"webinar|session|training|event|start|begin|go live|to go|"
                             r"until|left|away|from now|kick", ctx):
                continue
            num, unit = int(m.group(1)), m.group(2)
            stated = num*1440 if unit.startswith("day") else num*60 if unit[0] == "h" else num
            if abs(stated - actual) > 60:
                out.append(f"R8 body says ~{num} {unit} to the webinar but it sends "
                           f"{actual//60}h{actual%60:02d}m before")
                break
    # (c) phase language vs phase
    post_words = re.search(r"thanks for (join|attend)|missed (it|you|the)|in case you missed|"
                           r"replay|recording|watch (the|it|) ?(again|back)", low)
    pre_words = re.search(r"see you (there|soon|inside|live)|don'?t miss|save your (seat|spot)|"
                          r"starts? (in|soon|today|tomorrow)|join us live|"
                          r"happening (today|tomorrow|soon|now)|reminder|register now", low)
    if off < 0 and post_words and not pre_words:
        out.append("R8 PRE email but body reads like a post-webinar follow-up")
    if off >= 0 and pre_words and not post_words:
        out.append("R8 POST email but body reads like a pre-webinar reminder")
    return out

def _fetch_body_html(loc, tid):
    """Best-effort fetch of an email template's HTML for the §6a body checks."""
    if not tid: return ""
    try:
        b = next((x for x in _builders(loc) if x.get("id") == tid), None)
        if not b: return ""
        url = b.get("previewUrl")
        if not url: return ""
        code, body = _req("GET", url, {})
        return body if code == 200 else ""
    except SystemExit:
        return ""

def cmd_audit_emails(loc, wf):
    """§6a checks: R1 send-time window, R2 same-day 4h spacing, R3 unsubscribe,
    R4 webinar time (PRE only), R5 webinar name (PRE only), R6 phase CTA button,
    R7 monotonic order, R8 content-vs-schedule consistency. Body checks (R3-R6, R8)
    need the services/PIT token; the R1 window check needs the event date to be set.
    Phase = signed offset vs the webinar start; CTA-type and R8 detection are
    heuristic — flag and ask the user, don't auto-edit."""
    d = get_workflow(loc, wf)
    t = d["workflowData"]["templates"]
    by_id = {n.get("id"): n for n in t}
    start = next((n for n in t if n.get("type") == "event_start_date"), None)
    ev = _event_start(d)
    # walk the linear chain; each wait sets the current signed offset
    chain, seen = [], set()
    cur = (start.get("next") if start else (t[0].get("id") if t else None))
    off = 0
    while cur and cur in by_id and cur not in seen:
        seen.add(cur); n = by_id[cur]
        if n.get("type") == "wait":
            off = _wait_offset(n)
        if n.get("type") == "email":
            chain.append((off, n))
        cur = n.get("next")
        if isinstance(cur, list): cur = cur[0] if cur else None

    have_pit = os.path.exists(PIT_FILE)
    print(f"audit-emails: {len(chain)} email node(s) | event_start "
          f"{ev.isoformat() if ev else 'NOT SET (R1 window check skipped)'}"
          f"{'' if have_pit else ' | body checks skipped (no ~/.ghl-pit)'}")
    flags = 0
    for off_, n in chain:
        ph = _phase(off_)
        sign = "-" if off_ < 0 else "+"
        days = abs(off_) // 1440; hh = (abs(off_) % 1440) // 60; mm = abs(off_) % 60
        send = ev + timedelta(minutes=off_) if ev else None
        clock = send.strftime("%a %H:%M") if send else "?"
        issues = []
        # R1 — send-time window
        if send is not None and not _in_window(send.hour * 60 + send.minute):
            issues.append(f"R1 send {send.strftime('%H:%M')} outside 08-09/15-16/20-21")
        if have_pit:
            html = _fetch_body_html(loc, (n.get("attributes") or {}).get("template_id"))
            low = html.lower()
            has_btn, cal, zoom = _cta(html)
            # R3 — unsubscribe (all phases)
            if "{{unsubscribe}}" not in low and "unsubscribe" not in low:
                issues.append("R3 no unsubscribe")
            # R4 / R5 — webinar time + name, PRE-webinar only
            if ph != "POST":
                if not re.search(r"webinar_time|\d{1,2}\s*[:.]\s*\d{2}|\d{1,2}\s*(am|pm)", low):
                    issues.append("R4 no webinar time")
                if "webinar_name" not in low:
                    issues.append("R5 no webinar name (verify literal name)")
            # R6 — CTA button by phase (heuristic)
            if not has_btn:
                issues.append("R6 no CTA button")
            elif ph == "PRE-far":
                if not cal:  issues.append("R6 PRE-far should use an Add-to-Calendar button")
                if zoom:     issues.append("R6 PRE-far has a Zoom button (should be calendar)")
            elif ph == "PRE-near":
                if not zoom: issues.append("R6 PRE-near should use a Zoom/join button")
                if cal:      issues.append("R6 PRE-near has a calendar button (should be Zoom)")
            elif ph == "POST":
                if zoom or cal: issues.append("R6 POST must not have a Zoom/Calendar button")
            # R8 — content vs schedule consistency
            issues += _content_time_flags(low, off_, send)
        print(f"  {ph:8} {sign}{days}d {hh:02d}:{mm:02d} @ {clock} | {n.get('name')}"
              + ("  [OK]" if not issues else "  [FLAG] " + "; ".join(issues)))
        flags += len(issues)

    # R7 — strictly increasing send order
    offs = [o for o, _ in chain]
    if any(offs[i] >= offs[i+1] for i in range(len(offs)-1)):
        print("  [FLAG] R7 send order not strictly increasing"); flags += 1
    # R2 — same-day pairs < 4h apart
    for i in range(len(chain)-1):
        (c1, n1), (c2, n2) = chain[i], chain[i+1]
        if ev:
            s1, s2 = ev + timedelta(minutes=c1), ev + timedelta(minutes=c2)
            gap = (s2 - s1).total_seconds() / 60
            same_day = s1.date() == s2.date()
        else:
            gap = c2 - c1; same_day = c1 // 1440 == c2 // 1440
        if same_day and gap < MIN_GAP_MIN:
            print(f"  [FLAG] R2 same-day gap {gap:.0f}min < 240min: "
                  f"'{n1.get('name')}' -> '{n2.get('name')}' (collision — ask user to resolve)")
            flags += 1
    print(f"audit-emails: {flags} flag(s)." + ("" if flags else " All §6a checks passed."))

def cmd_set_event_date(loc, wf, iso):
    def fn(d):
        n = next(x for x in d["workflowData"]["templates"] if x.get("type") == "event_start_date")
        n["attributes"]["value"] = iso
    print(modify_and_put(loc, wf, fn))

def cmd_cv_list(loc):
    code, body = _req("GET", f"{SVC_BASE}/locations/{loc}/customValues", svc_headers())
    for c in json.loads(body).get("customValues", []):
        print(f"  {c.get('fieldKey'):45} = {c.get('value')!r}  (id {c.get('id')})")

def cmd_cv_create(loc, name, value):
    code, body = _req("POST", f"{SVC_BASE}/locations/{loc}/customValues",
                      svc_headers(ct=True), {"name": name, "value": value})
    c = json.loads(body).get("customValue", {})
    print(f"[{code}] key={c.get('fieldKey')} value={c.get('value')!r} id={c.get('id')}")

def _create_template(loc, title, html):
    code, body = _req("POST", f"{SVC_BASE}/emails/builder", svc_headers(ct=True),
                      {"locationId": loc, "title": title, "type": "html"})
    if code not in (200, 201): sys.exit(f"create template failed {code}: {body[:300]}")
    tid = json.loads(body)["id"]
    code2, body2 = _req("POST", f"{SVC_BASE}/emails/builder/data", svc_headers(ct=True),
                        {"locationId": loc, "templateId": tid, "updatedBy": "skill",
                         "html": html, "editorType": "html"})
    if code2 not in (200, 201): sys.exit(f"save template data failed {code2}: {body2[:300]}")
    return tid, code2

def cmd_email_create(loc, title, htmlfile):
    tid, code2 = _create_template(loc, title, open(htmlfile, encoding="utf-8").read())
    print(f"template_id={tid}  save=[{code2}]")

def _email_attrs(wf, node_id, subject, preheader, tid):
    return {"subject": subject, "template_id": tid, "templatesource": "email-builder",
            "from_email": "", "from_name": "", "previewUrl": "", "createdAt": "",
            "syncEnabled": False,
            "trackingOptions": {"hasTrackingLinks": False, "hasUtmTracking": False,
                                "hasTags": False, "sourceId": f"{wf}:{node_id}"},
            "conditions": [], "preHeader": preheader, "attachments": []}

def cmd_point_template(loc, wf, node_id, template_id, subject=None, preheader=None):
    def fn(d):
        n = next(x for x in d["workflowData"]["templates"] if x.get("id") == node_id)
        a = n["attributes"]
        a["template_id"] = template_id
        a["templatesource"] = "email-builder"
        a.pop("html", None)
        if subject is not None:   a["subject"] = subject
        if preheader is not None: a["preHeader"] = preheader
    print(modify_and_put(loc, wf, fn))

def _builders(loc):
    code, body = _req("GET", f"{SVC_BASE}/emails/builder?locationId={loc}&limit=100", svc_headers())
    if code != 200: sys.exit(f"list builders failed {code}: {body[:300]}")
    return json.loads(body).get("builders", [])

def cmd_templates(loc):
    for b in _builders(loc):
        print(f"  {b.get('id')} | {b.get('name')}")

def cmd_template_html(loc, template_id):
    b = next((x for x in _builders(loc) if x.get("id") == template_id), None)
    if not b: sys.exit(f"template {template_id} not found in this location")
    url = b.get("previewUrl")
    if not url: sys.exit("template has no previewUrl")
    code, body = _req("GET", url, {})
    if code != 200: sys.exit(f"fetch previewUrl failed {code}")
    sys.stdout.write(body)

def _distributed(total_min):
    total_min = int(total_min)
    return {"months": 0, "days": total_min // 1440,
            "hours": (total_min % 1440) // 60, "minutes": total_min % 60}

def cmd_add_email_after(loc, wf, after_id, title, htmlfile, wait_minutes, subject="", preheader=""):
    tid, _ = _create_template(loc, title, open(htmlfile, encoding="utf-8").read())
    wait_min = int(wait_minutes)
    new_email_id = str(uuid.uuid4())
    new_wait_id = str(uuid.uuid4()) if wait_min > 0 else None
    def fn(d):
        t = d["workflowData"]["templates"]
        after = next(x for x in t if x.get("id") == after_id)
        old_next = after.get("next")
        order = max((n.get("order", 0) or 0) for n in t)
        email_node = {"id": new_email_id, "order": order + (2 if new_wait_id else 1),
                      "attributes": _email_attrs(wf, new_email_id, subject, preheader, tid),
                      "name": title, "type": "email",
                      "next": old_next, "parentKey": new_wait_id or after_id}
        if new_wait_id:
            wait_attrs = {"type": "appointment", "name": title + " — wait", "cat": "",
                          "appointmentStartAfter": {"when": "after", "type": "minutes",
                              "value": wait_min, "distributed": _distributed(wait_min)},
                          "appointmentCondition": "skip", "isHybridAction": True,
                          "hybridActionType": "wait", "convertToMultipath": False,
                          "transitions": []}
            wait_node = {"id": new_wait_id, "order": order + 1, "attributes": wait_attrs,
                         "name": wait_attrs["name"], "type": "wait",
                         "next": new_email_id, "parentKey": after_id, "cat": ""}
            after["next"] = new_wait_id
            t.append(wait_node)
        else:
            after["next"] = new_email_id
        t.append(email_node)
    res = modify_and_put(loc, wf, fn)
    print(f"template_id={tid}  wait={new_wait_id}  email={new_email_id}  put=[{res}]")
    print("reminder: run `audit-emails` to confirm §6a (unsubscribe/webinar time/name/4h/order).")

def cmd_trigger_link(loc, name, url):
    code, body = _req("POST", f"{SVC_BASE}/links/", svc_headers(ct=True),
                      {"locationId": loc, "name": name, "redirectTo": url})
    print(f"[{code}] {body[:300]}")

CMDS = {
    "scan": cmd_scan, "nodes": cmd_nodes, "audit-emails": cmd_audit_emails,
    "set-event-date": cmd_set_event_date,
    "cv-list": cmd_cv_list, "cv-create": cmd_cv_create,
    "email-create": cmd_email_create, "point-template": cmd_point_template,
    "templates": cmd_templates, "template-html": cmd_template_html,
    "add-email-after": cmd_add_email_after, "trigger-link": cmd_trigger_link,
}

if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in CMDS:
        print(__doc__); sys.exit(1)
    CMDS[sys.argv[1]](*sys.argv[2:])
