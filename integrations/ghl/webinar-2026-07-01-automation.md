# GHL Automation — Webinar 1 July 2026 (Lena Forén / Lekluft)

> Node map + build sheet for the **3rd live webinar**: *"Det svåraste är inte barnets reaktion – utan det som händer i dig"*
> **Webinar:** 1 July 2026, **20:00 Europe/Stockholm** (T). Product: Relation före Reaktion™ (6 995 SEK).
> Build in **GHL → Automation → Workflows → Create from scratch**. All Wait steps anchor to `{{contact.webinar_date__time}}` with timezone **Europe/Stockholm**.
>
> Because this webinar starts in the **evening (20:00)** — not morning like 14 June — the day-of SMS/email offsets below are relative (T-3h = 17:00, T-1h = 19:00, T-10m = 19:50).

## Merge fields
| Use | Field |
|---|---|
| Email join link (long Zoom URL) | `{{contact.webinar_join_link}}` |
| SMS join link (Short.io) | `{{contact.webinar_join_link_short}}` |
| Date/time | `{{contact.webinar_date__time}}` |

---

## Workflow node map

```
Trigger: tag webinar-0701-registered
   │
   ▼
[If/Else] join_link empty? ──yes──> Tag missing-link + alert Lena
   │ no
   ▼
Email: Registration confirmation              (immediate)
   │
   ├─ Wait T-5d  → BWE1  Welcome (Jun 26)
   ├─ Wait T-3d  → BWE2  Value / story (Jun 28)
   ├─ Wait T-1d  → BWE3  "Imorgon 20:00" + link
   ├─ Wait T-3h  → BWE4  "Ikväll 20:00" + link      ╌╌> SMS1  17:00  "Idag 20:00 -> {short}"
   ├─ Wait T-1h  → BWE5  "Startar om 1 timme"        ╌╌> SMS2  19:00  "Om 1 timme -> {short}"
   ├─ Wait T-10m → BWE6  "Logga in nu"               ╌╌> SMS3  19:50  "Logga in nu -> {short}"
   └─ Wait T     → BWE7  "Vi är live" + link
   │
   ▼
========  WEBINAR LIVE — 1 Jul 20:00  ========
   │ after
   ▼
AWE1  Tack + replay        (T+2h)
AWE2  Recap + erbjudande   (T+1d)
AWE3  Story / invändning   (T+2d)
AWE4  "Stänger snart"      (T+3d)
AWE5  "Sista chansen"      (T+4d)
   │
   ▼
[Goal] purchased? ── tag `purchased` removes contact from the AWE sequence at any step
```

---

## Before-webinar emails (7)
| Node | Wait until | Email | Link |
|---|---|---|---|
| BWE1 | T − 5 days | Welcome / what you'll learn | — |
| BWE2 | T − 3 days | Value / story | — |
| BWE3 | T − 1 day | "Imorgon kl 20:00 – lägg in i kalendern" | ✅ join |
| BWE4 | T − 3 h | "Ikväll kl 20:00" | ✅ join |
| BWE5 | T − 1 h | "Startar om 1 timme" | ✅ join |
| BWE6 | T − 10 min | "Vi börjar strax – logga in nu" | ✅ join |
| BWE7 | T (00:00) | "Vi är live nu" | ✅ join |

## 3 reminder SMS (webinar day) — `{{contact.webinar_join_link_short}}`
| SMS | Send | Copy (GSM-7 safe, use `->` not `→`) |
|---|---|---|
| SMS1 | 17:00 (T-3h) | `Paminnelse: ikvall 20:00. Logga in: {{contact.webinar_join_link_short}}` |
| SMS2 | 19:00 (T-1h) | `Startar om 1 timme. {{contact.webinar_join_link_short}}` |
| SMS3 | 19:50 (T-10m)| `Vi borjar strax - logga in nu -> {{contact.webinar_join_link_short}}` |

> SMS via native GHL **Send SMS** (gives delivery reports) or a **Webhook** action to ClickSend (`POST rest.clicksend.com/v3/sms/send`, sender `LenaForen`) for parity with the current stack. Guard each SMS with an If/Else on `webinar_join_link_short` Is Empty → skip + tag `sms-no-link`.

## After-webinar emails (5)
| Node | Wait | Email | Links |
|---|---|---|---|
| AWE1 | T + 2 h | "Tack + replay" | `lekluft.com/repris` |
| AWE2 | T + 1 day | Recap + erbjudande | `lekluft.com/grunden` |
| AWE3 | T + 2 days | Story / invändning | `lekluft.com/grunden` |
| AWE4 | T + 3 days | "Stänger snart" | `lekluft.com/borja` |
| AWE5 | T + 4 days | "Sista chansen" | `lekluft.com/borja` |

**Goal (workflow-level):** tag `purchased` (set by the Stripe webhook) → contact exits the AWE sequence so buyers stop being pitched.

---

## Carried-over fixes (from the funnel audit)
- All Wait steps + location set to **Europe/Stockholm** (config previously read Europe/Oslo).
- SMS copy uses `->` and ASCII-safe text to stay GSM-7 single-segment.
- Empty-join-link guard alerts before BWE3 (first link-bearing email).
- Short.io auth header is the raw key — **no** `Bearer` prefix.
- DKIM still not configured on lekluft.com — enable in One.com + add record in Cloudflare to protect open rates.

## Build checklist
- [ ] Create/confirm tag `webinar-0701-registered` (Worker adds it on registration).
- [ ] Confirm `webinar_join_link`, `webinar_join_link_short`, `webinar_date__time` populated.
- [ ] Build the workflow nodes above; set every Wait to Europe/Stockholm.
- [ ] Choose SMS path (native GHL vs ClickSend webhook).
- [ ] Add the `purchased` goal exit.
- [ ] Test end-to-end with a test contact before publishing.
