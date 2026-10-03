# Sabeeli API contract

The HTTP and WebSocket contract between `frontend/src` and `backend/app`. It describes the code as it is now.
Interactive docs from the running server: `/api/docs` (OpenAPI JSON at `/api/openapi.json`).

- **Base path:** every HTTP route is under `/api`. The only WebSocket is `/ws/call/{id}`. In dev, Vite proxies both to `:8000`.
- **Format:** JSON in and out unless noted (`/api/ask` takes multipart form data, `/api/meetups/{id}/ics` returns `text/calendar`).
- **Auth** (`frontend/src/core/api.js` adds these headers):
  - **seeker:** an anonymous token from `POST /api/session`, sent as the `X-Seeker: <token>` header. The frontend keeps it in localStorage. On a 401 it forgets the token, makes a new session and retries once.
  - **daai:** a signed token from `POST /api/daai/login`, sent as `Authorization: Bearer <token>`. The frontend keeps it in sessionStorage.
  - **admin:** a da'i token whose profile has `role: "admin"`.
  - **none:** public. **seeker?** means the header is optional and only adds personal fields (`membership`, `my_rsvp`).
- **Errors:** `{"detail": "<message>"}` with the status code: 400 bad input, 401 `no session` / `unknown session` / `login required`, 403 forbidden, 404 not found (also used for "not yours"), 409 conflict, 413/415 image upload, 422 moderation, 500 `server error`. FastAPI's own validation errors are also 422, but their `detail` is an **array** of `{loc, msg, type}`.
- **Timestamps:** ISO 8601 UTC with a `Z` suffix, e.g. `"2026-10-04T18:00:00Z"`.

---

## Auth — owner: Eman

`backend/app/features/auth/routes.py` (sessions, login, profile). `GET /api/health` lives in `backend/app/main.py`, which is shared.
Other backend features use auth only through `backend/app/features/auth/public.py` (`seeker`, `optional_seeker`, `daai`, `optional_daai`, `admin`, `daai_from_token`, `seeker_id`, `Daai`, `SeekerSession`).

| Method | Path | Auth | Body / params | Returns |
|---|---|---|---|---|
| POST | `/api/session` | none | – | `{token}` (new anonymous seeker token) |
| DELETE | `/api/me` | seeker | – | `{ok: true}`. Deletes everything tied to the session in every feature (`SESSION_PURGERS`), then the session itself |
| POST | `/api/daai/login` | none | `{username, password}` | `{token, me: Profile}`. 401 on wrong credentials |
| GET | `/api/daai/me` | daai | – | Profile |
| POST | `/api/daai/availability` | daai | `{available: bool}` | Profile |
| GET | `/api/health` | none | – | `{ok, ai: bool, model: string\|null, corpus: {quran_verses, hadiths, terms, qa, bayyinat}}` |

Every authenticated da'i request updates `last_seen`. That is what makes a da'i count as "online" for `/api/availability` (see Calls).

## RAG — owner: Mushari

`backend/app/features/rag/routes.py`

| Method | Path | Auth | Body / params | Returns |
|---|---|---|---|---|
| POST | `/api/ask` | seeker | multipart: `question` (text; may be empty if `image` is sent), `lang` (`ar`, anything else means `en`; default `ar`), `image?` (JPEG/PNG/WebP/GIF, max 5 MB) | Answer. 400 `empty question`, 413 image too large, 415 unsupported image type |
| POST | `/api/ask/{turn_id}/feedback` | seeker (owner of the turn) | `{helpful: bool, reason?: string ≤ 64}` | `{ok: true}`. 404 if the turn isn't yours |
| GET | `/api/sources/{id}` | none | `id` = `q:2:256`, `h:2962`, `t:tawhid`, `qa:36065`, `b:12`; `?lang=ar\|en` (default `ar`) | Source card. 404 for an unknown id |
| GET | `/api/corpus` | none | – | `{quran_verses, hadiths, terms, qa, bayyinat, semantic_search}` (`bayyinat` is 0 until the copy has run `scripts/ingest_bayyinat.py`; `semantic_search` is a status string such as `on (intfloat/multilingual-e5-large, cuda, dense 70% + BM25 30%)`, `loading` or `off`) |

**Python interface (not HTTP).** Calls and Community import only from `features/rag/public.py`:
`conversation_transcript(db, session_id)`, `last_question(db, session_id) -> (question, source_ids)`, `source_exists(id)`,
`source_card(id, lang) -> card | None`, `answer_in_group(question, lang) -> Answer` (no `turn_id`). These signatures are part of the contract too.

## Community — owner: Mushari

`backend/app/features/community/routes.py`

| Method | Path | Auth | Body / params | Returns |
|---|---|---|---|---|
| GET | `/api/groups` | seeker? | `?lang=&country=&ui=ar\|en` | `[Group]` (active groups only) |
| GET | `/api/groups/{gid}` | seeker? | `?ui=` | Group. 404 if missing or inactive |
| POST | `/api/groups/{gid}/join` | seeker | `{nickname: 2–40 chars, accept_rules: bool}` | Group with `membership`. 400 if the rules aren't accepted or the nickname is rejected, 409 if the nickname is taken. Joining again only changes the nickname |
| POST | `/api/groups/{gid}/leave` | seeker | – | `{ok: true}` |
| GET | `/api/groups/{gid}/messages` | a member seeker, or the group's leader da'i | `?after=<last id>` (default 0) | `[GroupMessage]`, oldest first, at most 200. 403 if you are neither |
| POST | `/api/groups/{gid}/messages` | seeker (member) | `{text: ≤ 2000, lang: ar\|en}` | GroupMessage plus `redacted: bool`. 403 `join the group first` / `muted`. 422 with detail `too_long` \| `too_fast` \| `abuse` \| `empty` (3 `abuse` strikes mute the member). A message mentioning `@سبيلي` / `@sabeeli` gets a bot reply posted later in the background; poll to see it |
| GET | `/api/daai/groups` | daai | – | `[Group + needs_leader: int]` (the groups I lead) |
| POST | `/api/daai/groups` | daai | `{title: 3–160, description?, lang, country?, city?, audience: all\|women\|men}` | Group |
| POST | `/api/daai/groups/{gid}/messages` | daai (leader) | `{text}` | GroupMessage |
| POST | `/api/daai/groups/{gid}/messages/{mid}/delete` | daai (leader) | – | `{ok: true}` (soft delete) |
| POST | `/api/daai/groups/{gid}/messages/{mid}/resolve` | daai (leader) | – | `{ok: true}` (clears `needs_leader`) |
| POST | `/api/daai/groups/{gid}/members/{member_id}/mute` | daai (leader) | `{muted: bool}` | `{ok: true, muted}` |
| GET | `/api/meetups` | seeker? | `?country=&city=&lang=&ui=` | `[Meetup]`: status `open`, starting no earlier than 3 h ago, soonest first |
| POST | `/api/meetups/{mid}/rsvp` | seeker | `{nickname: 2–40, confirm_audience?: bool}` (must be `true` for `women` / `men` meetups) | Meetup with `my_rsvp`. Safe to repeat. 400, 404, 409 `full` |
| POST | `/api/meetups/{mid}/cancel-rsvp` | seeker | – | `{ok: true}` |
| GET | `/api/meetups/{mid}/ics` | none | – | `text/calendar` attachment (linked with a plain `<a href download>`) |
| GET | `/api/daai/meetups` | daai | – | `[Meetup + attendees: [nickname]]` (meetups I host, in any status) |
| POST | `/api/daai/meetups` | daai | `{title: 3–160, description?, lang, country?, city: 2–64, venue: 3–200, starts_at: ISO 8601 (no offset = UTC), duration_min: 15–480 (default 90), capacity: 2–500 (default 20), audience: all\|women\|men\|families, group_id?: int\|null, public_venue: true}` | Meetup. 400 if `public_venue` isn't true, the audience is bad, or the group isn't yours |
| POST | `/api/daai/meetups/{mid}/cancel` | daai (host) | – | `{ok: true}` |

## Videos — owner: Mushari

`backend/app/features/videos/routes.py`, backed by `islamhouse.py`. Public (no auth). Data comes live from the IslamHouse API v3 (listed on page 9 of the scholarly package). Arabic and English are indexed in the background at startup; any other language is indexed on its first request (15–35 s), at most 3 languages at a time (a language waiting for its turn stays `loading`). After that everything is served from memory for 6 hours. Once the language list has loaded, a `lang` that isn't in it falls back to `ar`. If IslamHouse can't be reached, the state is `unavailable` and the server waits 60 s before trying again; the language list does the same and keeps serving its last good copy. The API key can be overridden with `SABEELI_ISLAMHOUSE_KEY`.

| Method | Path | Auth | Body / params | Returns |
|---|---|---|---|---|
| GET | `/api/videos` | none | `lang` (an IslamHouse language code, e.g. `ar`, `en`, `ur`, `fr`, `zh`; default `ar`), `page` (default 1), `per_page` (1–48, default 12), `topic?` (a topic id from `topics`) | `{state, items: [Video], page, pages, total, topics: [{id, title, count}], source: {name, url}}`. `state` is `loading` while the index is built (the client polls every 2 s; `items` is empty), `ready`, or `unavailable` when IslamHouse can't be reached |
| POST | `/api/videos/search` | none | JSON `{lang, q, topic?, page?, per_page?}` (`q` max 100 chars) | Same as `GET /api/videos`, filtered by the search words. A POST body so search words never reach access logs; searches are not stored |
| GET | `/api/videos/languages` | none | – | `[{code, name, count}]`: every language with videos, native name, largest first (107 languages today). 503 `unavailable` |

Search: every word must appear in the title, description, presenters or topic; title matches rank first, then the newest. Arabic text is compared through `core/textnorm.normalize_ar` (hamza, taa marbuta, diacritics) and a leading «ال» is ignored; other scripts are case- and accent-folded. IslamHouse's API has no search endpoint, so this runs on the cached index.

## Calls — owner: Eman

`backend/app/features/calls/routes.py`, `referral.py`. Supported call languages: `ar en fr ur id tr es de bn ru zh sw ha so fa`.

| Method | Path | Auth | Body / params | Returns |
|---|---|---|---|---|
| GET | `/api/availability` | none | – | `{languages: {<lang>: {total, m, f}}}`. Counts da'is with role `daai` who are `available` and were seen in the last 90 s |
| GET | `/api/rtc-config` | none | – | `{iceServers: [{urls, username?, credential?}], iceTransportPolicy: "all"\|"relay"}`. Pass it straight to `RTCPeerConnection` |
| POST | `/api/referral/draft` | seeker | `{lang: ar\|en}` | `{id, mode: "model"\|"template"\|"none", card: ReferralCard}`. The experiment arm rotates when the experiment is on; `model` falls back to `template` without AI |
| POST | `/api/referral/{rid}/confirm` | seeker (owner) | `{consent: bool, card: ReferralCard}` | `{ok: true, consented}`. The card is cleaned (lengths capped, unknown source ids dropped). The da'i sees nothing unless `consent` is true |
| POST | `/api/calls` | seeker | `{lang, gender_pref: ""\|"m"\|"f", referral_id?: int\|null}` | `{id, status: "waiting"}`. Cancels your earlier waiting request. 400 for an unsupported language or preference, 404 if the referral isn't yours |
| GET | `/api/calls/{cid}` | seeker (owner) | – | CallStatus. Also turns `waiting` into `expired` after `CALL_WAIT_SECONDS` (default 600) |
| POST | `/api/calls/{cid}/cancel` | seeker (owner) | – | CallStatus. `waiting` becomes `cancelled`, `accepted` becomes `ended` (the da'i gets no WebSocket notice) |
| POST | `/api/calls/{cid}/rate` | seeker (owner) | `{rating: int}` (clamped to 1–5) | `{ok: true}` |
| GET | `/api/calls/{cid}/messages` | seeker (owner) | – | `[{id, sender: "seeker"\|"daai", text, at}]` (in-call chat history) |
| GET | `/api/daai/requests` | daai | – | `{waiting: [{id, lang, waiting_seconds, has_card}], active: [{id, lang}]}`. Lists only requests that match my languages and the requested gender |
| POST | `/api/daai/requests/{cid}/accept` | daai | – | DaaiCall. 404 if it doesn't match me, 409 `already taken or no longer waiting` |
| GET | `/api/daai/calls/{cid}` | daai (assigned) | – | DaaiCall |
| POST | `/api/daai/calls/{cid}/understood` | daai (assigned) | – | `{ok: true}` |
| POST | `/api/daai/calls/{cid}/end` | daai (assigned) | `{reexplain_needed?: bool\|null, card_accurate?: bool\|null, note?: string}` (note cut to 500 chars) | `{ok: true}`. Ends the call if it is accepted and stores the feedback |
| GET | `/api/daai/experiment` | daai | – | `{enabled, arms: {<model\|template\|none\|direct>: {calls, no_reexplain_rate, card_accurate_rate, median_seconds_to_understand}}, waiting_now}` |
| POST | `/api/daai/experiment` | admin | `{enabled: bool}` | `{enabled}`. 403 `admin only` |

Call status values: `waiting` → `accepted` → `ended`, or `cancelled` / `expired`.

## WebSocket signalling — owner: Eman

`backend/app/features/calls/signalling.py`, client `frontend/src/features/calls/room.js`

**URL:** `ws(s)://<host>/ws/call/{id}?role=seeker|daai&token=<token>`. Use the raw seeker token for a seeker and the da'i token (without `Bearer `) for a da'i.

**Who may connect:** only the two people in an **accepted** call: the seeker who owns it and the da'i assigned to it. Anyone else is closed with code 4003 before the handshake completes (see Notes). If the same role connects again, the newer socket replaces the older one, and the older one is closed with code 4001. Rooms live in memory, so run one worker.

**Client → server**

| `type` | Server does |
|---|---|
| `offer`, `answer`, `ice`, `bye`, `mute`, `ready` | Relays the whole JSON object unchanged to the other peer, but only if they are connected (nothing is queued). The client uses `{type:"offer"\|"answer", sdp}` and `{type:"ice", candidate}` |
| `chat` `{text}` | Trims the text and caps it at 1000 chars (empty text is ignored), stores it, then sends `{type:"chat", id, sender, text, at}` to **both** peers, sender included |
| `end` | Marks the call `ended` (if it is accepted) and sends `{type:"ended", by: role}` to the other peer |
| anything else, bad JSON, or > 64 000 chars | Ignored |

**Server → client:** `{type:"joined", role, present: [roles in the room, including you]}` when you connect, `{type:"peer-joined", role}` and `{type:"peer-left", role}` for the other side, `{type:"ended", by}`, `{type:"chat", ...}`, plus the relayed messages above.

**Who offers:** the da'i sends the offer, either on `joined` when `present` already contains `"seeker"`, or on `peer-joined` (with an ICE restart if the connection had failed). The seeker only answers.

---

## Shapes

### Answer (`POST /api/ask`)

```json
{
  "turn_id": 42,
  "kind": "answer",
  "mode": "ai",
  "lang": "en",
  "level": "B",
  "segments": [
    {"text": "General explanation from the sources...\n[[q:2:256]]\n", "cites": ["q:2:256"]},
    {"text": "More explanation...", "cites": ["h:2962", "t:tawhid"]}
  ],
  "cards": {"q:2:256": {"kind": "quran"}, "h:2962": {"kind": "hadith"}, "t:tawhid": {"kind": "term"}},
  "sources": ["q:2:256", "h:2962", "t:tawhid"],
  "quote_check": {
    "input": "the Arabic text the user quoted",
    "status": "differs",
    "matches": [{"ids": ["q:112:1"], "score": 0.857, "exact": false, "ambiguous": false,
                 "differences": [{"type": "changed", "quoted": "…", "reference": "…"}]}]
  },
  "notices": [{"type": "disagreement", "text": "..."}],
  "ocr": null,
  "suggest_daai": false,
  "trace": {"timings": {"analyze": 0.8, "retrieve": 0.01, "answer": 3.1, "total": 4.0},
            "analysis": {"queries_ar": [], "queries_en": []},
            "retrieval": [{"id": "q:2:256", "score": 12.3, "coverage": 0.6, "via": "search"}],
            "cited_share": 0.9}
}
```

- `kind`: `answer` | `sources` | `abstain` | `refer` | `clarify` | `greeting` | `thanks` | `off_topic` | `request_human` | `empty`. `refer` is a personal (level D) question while the model is unavailable: a fixed message, the `fatwa` notice and `suggest_daai: true`, and no source cards.
- `mode`: `ai` | `sources_only` (no model: the passages are shown with no generated text). `lang`: the language detected from the question, which can differ from the UI language. `level`: `A`–`D` (`C` = scholars differ, `D` = personal case or fatwa; both set `suggest_daai`).
- `cards`: id → full source card (see below; shortened in the example). `sources`: every id used, in order of first use.
- `quote_check`: `null`, or `status` = `exact` | `differs` | `ambiguous` | `not_found` (`matches` is `[]` for `not_found`, otherwise up to 3). `differences[].type` = `changed` | `missing` | `extra`.
- `notices[].type`: `ocr` | `fatwa` | `disagreement` | `mode`.
- `ocr`: `null`, or `{text, quran_segments: [string], description, legible: bool}` when a photo was read.
- `trace`: for debugging and the "how was this answered" sheet only. Its fields change freely; other features must not rely on them.

**Rendering rule:** segment `text` may contain `[[q:SURA:AYA]]`, `[[h:ID]]`, `[[t:key]]`, `[[qa:ID]]` and `[[b:N]]` markers. Render each marker as the card `cards[id]` (skip it if the card is missing), **never as text**. Scripture shown to the user only ever comes from cards. Each id in `cites` that isn't already shown as a card in that segment becomes a numbered citation button. Group bot messages carry the same structure in `payload`.

### Source cards (`cards[id]`, `GET /api/sources/{id}`, `card_sources`)

Every card has `id, kind, title, url, source`. Text in the requested language falls back to Arabic.

```json
{"id": "q:2:256", "kind": "quran", "title": "Quran 2:256 (Al-Baqarah)", "url": "https://…", "source": "Mushaf text (King Fahd Complex) and Rowwad translation via QuranEnc",
 "sura": 2, "aya": 256, "text_ar": "…", "tafsir_ar": "…", "translation_en": "…", "sura_name_ar": "البقرة", "sura_name_en": "Al-Baqarah"}

{"id": "h:2962", "kind": "hadith", "title": "Hadith: …", "url": "https://…", "source": "Encyclopedia of Translated Prophetic Hadiths (HadeethEnc)",
 "text_ar": "…", "text_en": "… or empty", "grade": "…", "attribution": "…", "explanation": "…"}

{"id": "t:tawhid", "kind": "term", "title": "Term: …", "url": "", "source": "<glossary source>",
 "term_ar": "…", "term_en": "…", "rule_ar": "…"}

{"id": "qa:36065", "kind": "qa", "title": "سؤال وجواب: …", "url": "https://islamenc.com/…", "source": "<encyclopedia>, icadb",
 "question": "…", "answer": "Arabic text with [[q:S:A]] markers", "verses": {"q:7:54": {"sura", "aya", "text_ar", "translation_en", "sura_name_ar", "sura_name_en"}},
 "categories": ["…"], "encyclopedia": "…"}

{"id": "b:12", "kind": "bayyinat", "title": "بيّنات: …", "url": "https://dawa.center/file/7937", "source": "«بينات…»، المسألة 12 (ص …)",
 "question": "…", "heading": "…", "short_answer": "… with markers", "answer": "… with markers", "verses": {}, "section": "…"}
```

`qa` and `bayyinat` answers are Arabic only. Inside `question`, `short_answer` and `answer`, a `[[q:S:A]]` marker is drawn from `verses[id]`, never as text. `SourceCard` from `features/rag/public.js` already renders both kinds.

### ReferralCard (`/api/referral/*`, `DaaiCall.card`)

```json
{"question": "…", "context": "…", "explained": [{"point": "…", "sources": ["q:2:256", "h:2962"]}], "unclear": "…", "language": "English"}
```

Limits after cleaning: `question`, `context` and `unclear` ≤ 600 chars, `language` ≤ 40, at most 6 `explained` items, each `point` ≤ 300 chars with at most 6 known source ids.

### CallStatus (seeker) and DaaiCall (da'i)

```json
{"id": 7, "status": "accepted", "lang": "en", "daai": {"name": "…", "name_en": "…", "gender": "m"},
 "queue_position": 0, "created_at": "2026-10-04T18:00:00Z"}
```

`daai` is `null` until the call is accepted. `queue_position` counts the waiting requests in the same language that are ahead of you.

```json
{"id": 7, "status": "accepted", "lang": "en", "card": "ReferralCard or null", "card_sources": {"q:2:256": "source card"},
 "referral_mode": "model|template|none|direct", "accepted_at": "…Z", "understood": false}
```

### Profile (da'i)

```json
{"id": 1, "username": "…", "name": "…", "name_en": "…", "gender": "m", "languages": ["ar", "en"], "role": "daai",
 "available": true, "bio": "…", "bio_en": "…", "is_demo": true}
```

`role` is `daai` | `admin`.

### Group

```json
{"id": 3, "title": "…", "description": "…", "lang": "en", "country": "", "city": "…", "audience": "all", "active": true,
 "members": 12, "leader": {"id": 1, "name": "…", "gender": "m", "languages": ["en"]}, "is_demo": true,
 "membership": {"id": 55, "nickname": "…", "muted": false}}
```

`membership` is `null` when the caller isn't a member (or sent no seeker token). `leader.name` follows `ui` (Arabic or English name).

### GroupMessage

```json
{"id": 901, "author_type": "bot", "author": "Sabeeli (AI assistant)", "member_id": null, "text": "…",
 "deleted": false, "payload": {"segments": [], "cards": {}, "sources": [], "notices": [], "kind": "answer",
 "level": "B", "mode": "ai", "quote_check": null, "lang": "en"}, "reply_to": 900, "needs_leader": false, "at": "…Z"}
```

- `author_type`: `seeker` | `daai` | `bot` (the model also allows `system`). `member_id` is set only for seekers.
- `payload` is `{}` except on bot answers. For bot answers, render `payload` with the Answer component, **not** `text`: `text` is the joined raw segment text and still contains the markers.
- `needs_leader` is true for bot answers at level C or D, or when the bot abstained. A deleted message has `text: ""` and `payload: {}`.

### Meetup

```json
{"id": 4, "title": "…", "description": "…", "lang": "en", "country": "", "city": "…", "venue": "…",
 "starts_at": "2026-10-10T16:00:00Z", "duration_min": 90, "capacity": 20, "going": 5, "spots_left": 15,
 "audience": "families", "host": {"id": 1, "name": "…", "gender": "f", "languages": ["en"]}, "group_id": null,
 "status": "open", "is_demo": true, "my_rsvp": {"code": "…", "nickname": "…"}}
```

`audience` is `all` | `women` | `men` | `families`, `status` is `open` | `cancelled`, and `my_rsvp` is `null` when you haven't booked.

---

### Video

```json
{"id": 2844735, "title": "صفة الحج", "description": "تطبيق عملي يوضح كيفية الحج خطوة بخطوة.",
 "thumbnail": "https://d1.islamhouse.com/data/ar/ih_videos/pic/pic_index/2844735.jpg", "authors": ["..."], "lang": "ar", "added": 1780566879,
 "parts": [{"kind": "mp4", "url": "https://d1.islamhouse.com/data/ar/ih_videos/mp4/single/ar_Description_of_the_Hajj.mp4", "label": "صفة الحج", "size": "194.11 MB"}],
 "page_url": "https://islamhouse.com/ar/videos/2844735/", "topic": "صفة الحج", "topic_id": 1234}
```

- `parts` has one entry per file (a series has several). `kind` is `mp4` (play with `<video>`) or `youtube` (an embed URL on `youtube-nocookie.com`). When an item has both, only the MP4s are kept; items with neither are dropped (IslamHouse lists some PDFs as videos).
- `description` is plain text (HTML stripped) and may be empty. `thumbnail` may 404 on IslamHouse's side; the page then shows a placeholder.
- `topic` is the most specific IslamHouse category the video was found under; `topic_id` is its top-level topic (an id from `topics`).

## Changing the contract

Some routes, shapes, WebSocket messages and `rag/public.py` functions are used by the other owner's code. Examples: source cards in the da'i call view and the referral sheet, the ReferralCard, Profile, the auth headers and `api.js`. Change one of those only after **both owners agree**, and update this file **in the same commit**. Things that only one owner uses can change freely, but keep this file accurate.

## Notes for the team

Review findings from 2 October 2026:
- **Fixed in the starting version:** stale docstring paths; WebSocket refusals now accept and then close with 4003, so `room.js` sees "refused"; message reading on inactive groups.
- **Moved to the task lists:**
  - `tasks/eman.md`: the da'i's chat history, notifying the da'i when a seeker cancels during a call, time-limited TURN credentials, and WebSocket tickets instead of tokens in the URL;
  - `tasks/mushari.md`: the `ui` language for leader and host names in community responses.
