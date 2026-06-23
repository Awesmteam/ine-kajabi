# GHL Automation — Webinar Registration & Nurture

> **Build sheet** for the GoHighLevel Workflow that drives the "Relation före reaktion — Grunden" webinar funnel.
> Translated from the System Setup Recap (Lena Forén / Lekluft). Build this in **Automation → Workflows → Create Workflow → Start from scratch**.
>
> GHL has no public workflow-import API, so this is a node-by-node spec to recreate in the visual builder. Three separate workflows are described:
>
> - **WF-1 — Registration & Nurture** (the main one; pre-webinar emails + SMS)
> - **WF-2 — After-Webinar Sales (AWE 1–9)**
> - **WF-3 — Sale Confirmation** (Stripe-driven)

---

## Config anchors (Settings → reference)

| Item | Value |
|---|---|
| Location ID | `jSaDcRCuAJsIXWPVKTgG` |
| Sender | Lena Forén `<lena@lekluft.com>` |
| Webinar date/time field | `{{contact.webinar_date__time}}` (single datetime custom field) |
| Long Zoom link (email) | `{{contact.webinar_join_link}}` |
| **NEW** short link (SMS) | `{{contact.webinar_join_link_short}}` — add this custom field (see §SMS) |
| Timezone | **Europe/Stockholm** — see Fix #2 |
| Entry tag (from Worker) | `webinar-registered` |

> The Cloudflare Worker already creates/upserts the contact and sets `webinar_join_link`, `webinar_date`, `webinar_time`, `webinar_date__time`, and enrolls the contact. WF-1 below replaces step 7 of the Worker flow ("Enroll in registration workflow").

---

## WF-1 — Registration & Nurture

### Trigger
- **Trigger:** `Contact Tag` → tag added is `webinar-registered`
  - (Alternative: keep the Worker's direct "add to workflow" enrollment — either path enters here.)
- **Workflow settings:** Allow re-entry = **Off**. Stop on response = Off.

### Node 1 — Guard: missing join link (Fix #4, fail-soft)
- **If/Else** condition: `webinar_join_link` **Is Empty**
  - **TRUE branch:**
    - **Add Tag:** `missing-join-link`
    - **Internal Notification** (Email → `lena@lekluft.com`): subject `⚠ Registrant utan join-länk: {{contact.email}}` — flags the fail-soft case so it can be back-filled before the broken-CTA emails go out.
    - Continue (do not drop the contact — they still get the sequence; CTA just needs back-fill).
  - **FALSE branch:** continue.

### Node 2 — Registration confirmation email (immediate)
- **Send Email**
  - From: `Lena Forén <lena@lekluft.com>`
  - Subject: `Du är anmäld – så här loggar du in`
  - CTA button → `{{contact.webinar_join_link}}`
  - Includes `{{contact.webinar_date__time}}` + add-to-calendar `{{contact.webinar_add_to_calendar_link}}`.

### Nodes 3–12 — Before-Webinar Emails (BWE 1–10)
Use **Wait → "Wait until a specific date/time"** anchored to the custom field `{{contact.webinar_date__time}}` with a relative offset. Each Wait precedes its Send Email. Suggested cadence across the 5-day window (T = webinar start):

| Node | Wait until | Email |
|---|---|---|
| 3 | T − 5 days | **BWE1** — "Välkommen / vad du kommer lära dig" |
| 4 | T − 3 days | **BWE2** — value / story |
| 5 | T − 1 day | **BWE3** — "Imorgon kl 09:30 – lägg in i kalendern" + join link |
| 6 | T − 3 hours | **BWE4** — "Idag kl 09:30" + join link |
| 7 | T − 1 hour | **BWE5** — "Om 1 timme" + join link |
| 8 | T − 30 min | **BWE6** — "Om 30 min – testa din länk" + join link |
| 9 | T − 15 min | **BWE7** — "Om 15 min" + join link |
| 10 | T − 5 min | **BWE8** — "Vi börjar strax – logga in nu" + join link |
| 11 | T (00:00 offset) | **BWE9** — "Vi är live nu" + join link |
| 12 | T + 5 min | **BWE10** — "Vi har börjat – hoppa in" + join link |

- Every CTA uses `{{contact.webinar_join_link}}` (long Zoom URL).
- Set Wait step **timezone = Europe/Stockholm** explicitly on each (Fix #2).

### SMS nodes (interleave with BWE on webinar day)
The recap sends SMS via **ClickSend** (sender `LenaForen`, alphanumeric — no replies/DLR). Two ways to do it in GHL:

**Option A (parity with current stack — ClickSend via Webhook action):**
- Add **Webhook** action `POST https://rest.clicksend.com/v3/sms/send`
  - Auth header: ClickSend Basic auth (username + API key).
  - Body: `to` = `{{contact.phone}}`, `from` = `LenaForen`, `body` = SMS copy with `{{contact.webinar_join_link_short}}`.

**Option B (simpler — native GHL SMS):** use a **Send SMS** node directly. Drops the ClickSend dependency and gives you GHL delivery reports. Recommended unless the `LenaForen` alphanumeric sender ID is contractually required.

| Wait until | SMS | Copy (GSM-7 safe) |
|---|---|---|
| T − 90 min (08:00) | **SMS2** | `Startar om 1 timme. Logga in: {{contact.webinar_join_link_short}}` |
| T − 15 min (09:15) | **SMS3** | `Logga in har nu -> {{contact.webinar_join_link_short}}` |
| T (09:30) | **SMS4** | `Vi har borjat! {{contact.webinar_join_link_short}}` |

- **Fix #3 (GSM-7):** use `->` not `→`, and avoid `å/ä/ö` where it forces UCS-2 / 2 segments if you need single-segment. (Copy above uses ASCII-safe forms; localize per segment budget.)
- **Short link field:** create custom field `webinar_join_link_short` and populate it (Short.io `join.lekluft.com/XXXXX`) either in the Worker or via a Webhook action that calls Short.io (`Authorization: <raw_key>`, **no** `Bearer` prefix — Fix from §4).

### Node end
- **Add Tag:** `webinar-nurture-complete`. WF-1 ends here; attendance tagging (`attended` / `no-show`) is set from the Zoom side or a manual import, and gates WF-2.

---

## WF-2 — After-Webinar Sales (AWE 1–9)

- **Trigger:** `Contact Tag` → `webinar-attended` **OR** `webinar-noshow` (the recap enrolls these manually after the webinar; a tag trigger makes it one-click).
- **Nodes:** 9 × (Wait → Send Email) for AWE1–AWE9. Cadence per the sales calendar (typically T+0 → T+5 days). Each links to the sales/checkout pages:
  - Sales page: `https://lekluft.com/grunden`
  - Checkout: `https://lekluft.com/borja`
- **Exit/Goal:** add a **Goal event / If-Else** on tag `purchased` → remove from sales sequence so buyers stop getting pitched.

---

## WF-3 — Sale Confirmation

- **Trigger:** `Inbound Webhook` from the Stripe webhook the Worker already handles (`/api/stripe/webhook`), or `Contact Tag` → `purchased` (Worker sets it on purchase).
- **Nodes:**
  1. **Send Email:** sale confirmation (from Lena Forén). Pull product/plan/amount from the purchase custom fields the Worker writes.
  2. **Add Tag:** `customer`; **Remove Tag:** `webinar-noshow` / sales tags.
  3. (Optional) Enroll in onboarding/fulfilment workflow for the 8-week program.

---

## Fixes carried over from §10 (Known Issues)

| # | Issue | Action in this build |
|---|---|---|
| 1 | SMS `{custom1}` could render literally | In GHL, an unresolved merge field renders **empty**, not literal. Add an If/Else guard on `webinar_join_link_short` Is Empty before each SMS; route empty → skip SMS + tag `sms-no-link`. |
| 2 | Timezone `Europe/Oslo` vs Stockholm | Set every Wait step and the location timezone to **Europe/Stockholm**. |
| 3 | `→` forces UCS-2 (2 segments) | SMS copy uses `->` and ASCII-safe text. |
| 4 | Fail-soft empty join link → broken CTA | Node 1 guard tags + notifies; back-fill before BWE3 (T−1 day) which is the first link-bearing email. |
| — | **DKIM not configured** (deliverability) | Out of scope for the workflow, but BWE/AWE open rates depend on it. Enable DKIM signing in One.com, add the CNAME/TXT to Cloudflare. Flag to Lena. |

---

## Build order checklist

- [ ] Create custom field `webinar_join_link_short` (text).
- [ ] Confirm Worker populates `webinar_join_link`, `webinar_date__time`, and (new) `webinar_join_link_short`.
- [ ] Build **WF-1** (trigger → guard → confirmation → 10 BWE waits/emails + 3 SMS).
- [ ] Build **WF-2** (tag trigger → 9 AWE → purchase goal exit).
- [ ] Build **WF-3** (Stripe/purchase trigger → confirmation).
- [ ] Decide ClickSend-webhook vs native GHL SMS (Option A vs B).
- [ ] Set all timezones to Europe/Stockholm.
- [ ] Test enrollment end-to-end with a test contact before publishing.
