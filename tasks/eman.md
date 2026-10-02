# Eman: task list

You own:

- **Auth**: anonymous seeker sessions, "delete my data", da'i login, accounts and the demo accounts.
- **The da'i interface**: the login screen and the whole da'i console (calls tab, groups tab, meetups tab).
- **Calls**: the seeker's call request, matching with an available da'i, the WebRTC audio room, the in-call text chat, and the **referral card** (the summary the seeker reviews before it is shared) with its experiment.

Your folders, and the only ones you edit without asking Mushari:

- `backend/app/features/auth/`, `backend/app/features/calls/`
- `frontend/src/features/daai/`, `frontend/src/features/calls/`
- `tests/auth/`, `tests/calls/`

The groups and meetups tabs call Mushari's community API. Use only the routes in `docs/API.md` and `frontend/src/features/community/public.js`; ask him for any API change.

Shared (`backend/app/core/`, `frontend/src/core/`, `frontend/src/styles/`, `frontend/src/pages/`, `frontend/src/App.jsx`, `docs/API.md`) changes only after agreeing with Mushari. From RAG you may use only `backend/app/features/rag/public.py` and `frontend/src/features/rag/public.js`. Other features use your auth only through `backend/app/features/auth/public.py`: keep its functions working.

Work on a branch named `eman/<topic>` and open a pull request into `main`.

Tick a box when the task is merged. Keep the order unless the team agrees otherwise.

## Before 4 October (setup, not judged)

- [ ] Run the app, sign in to the da'i console as `maryam`, and make a call to yourself from a second browser (one normal window and one private window). Check the audio and the text chat.
- [ ] Choose a TURN service for strict networks, and put its details in `.env` (`TURN_URL`, `TURN_USERNAME`, `TURN_CREDENTIAL`). Record the service in `THIRD_PARTY.md`.

## Auth and the da'i interface (moved to you on 2 October)

- [ ] **Da'i accounts:**
  - a way for the reviewer (admin) to add, disable and reset da'i accounts; today they come only from `features/auth/seed.py`;
  - a profile edit screen for a da'i's languages, bio and gender.
- [ ] **Login hardening:**
  - limit login attempts per username and IP;
  - set `SECRET_KEY` in deployment so tokens survive restarts;
  - log out everywhere on a password change.
- [ ] **Seeker sign-in (decide with Mushari first):** seekers are anonymous by design, which is a privacy promise on the Privacy page. If you add optional sign-in, keep anonymous use working, and update the Privacy page and `THIRD_PARTY.md`.
- [ ] **Da'i console UX:**
  - a dashboard summary (requests waiting, groups needing a reply, upcoming meetups);
  - a mobile layout check at 390px;
  - a clear "you're offline" state when the availability switch is on but the tab is closed.
- [ ] Tests in `tests/auth/` for every change.

## Day 1: 4 October (calls work everywhere)

- [ ] **Two networks test**: one person on home Wi-Fi and one on mobile data, with and without TURN. Write the results in `docs/CALLS-TEST.md`.
- [ ] Turn on `CALL_RELAY_ONLY=1` once TURN works, so neither side sees the other's IP address. Document the trade-off.
- [ ] When the audio cannot connect, offer a clear switch to text. The chat panel already works without audio; make the state obvious.
- [ ] **Da'i notifications**: play a sound and show a browser notification (with permission) when a request arrives while the console is in a background tab. The tab title already shows the count.
- [ ] Tests in `tests/calls/` for every change.

## Day 2: 5 October (referral card and experiment)

- [ ] Run the referral card with the real model. Check that the card never adds anything the seeker didn't say, and that the seeker can edit or remove every field. Tune `REFERRAL_SYSTEM` in `features/calls/referral.py`.
- [ ] Add a PII check before saving the final card: phone numbers, emails and links are removed, with a note to the seeker. The community feature has regex helpers you can copy into calls.
- [ ] **Referral experiment** (the core of our «التميّز» claim):
  - The reviewer account (`reviewer`) turns it on in the console.
  - Protocol: the same 8 questions, the same da'i, arms rotated (AI summary / fixed template / no summary).
  - Record for each call: re-explaining needed, time until "I understand the question", and card accuracy.
  - Target: **6 of 8 referrals without re-explaining** with the AI card, and better than both other arms.
- [ ] Write the protocol and results in `docs/REFERRAL-EXPERIMENT.md`, and show them in the console's experiment card.

## Known gaps found in review (2 October)

- [ ] The da'i has no chat-history endpoint: add `GET /api/daai/calls/{id}/messages`, so a da'i who reloads the page keeps the earlier chat. Pass it to `CallPanel` as `historyPath` for the da'i role.
- [ ] `POST /api/calls/{id}/cancel` during an accepted call ends the call, but nothing is sent to the da'i's socket. Notify the room, so the da'i sees "ended".
- [ ] `GET /api/rtc-config` is public and would return the TURN password. Use time-limited TURN credentials issued per call, for example from the TURN provider's REST API.
- [ ] WebSocket tokens travel in the URL. Consider a short-lived one-time ticket from `POST /api/calls/{id}/ticket` instead.

## Day 3: 6 October (polish and publish)

- [ ] Waiting screen: an estimated wait, and a clear message when no da'i speaks the chosen language right now (suggest groups instead).
- [ ] Mobile check of the whole call flow at 390px width.
- [ ] With Mushari: deploy, record the demo video (2 minutes or less), make the repo public, submit before **23:59 on 6 October (Riyadh time)**.

## Ideas if time allows

- [ ] Book a call slot with a da'i for later (the deck mentions it as future work).
- [ ] An audio level indicator in the call room, so people see the microphone works.
