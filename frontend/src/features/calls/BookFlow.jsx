// Talk page, "Book a time" (seeker): pick a language, a da'i (or anyone), a length, a day and a free time,
// review, confirm. Times show in the viewer's own time zone. Owner: Eman (calls).
import "./strings.js";
import "./calls.css";
import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "../../core/api.js";
import { useI18n } from "../../core/i18n.jsx";
import { Icon, Notice, Spinner, errorText, toast, usePolling } from "../../core/ui.jsx";
import { useAccount } from "../account/public.js";
import { CalendarButtons, daaiName } from "./MyBookings.jsx";
import { dayIso, localDay, nextDays, period, zoneName } from "./bookingUtils.js";

const LANGS = ["ar", "en"];
const DAYS = 15;   // today and the next 14

/** The bookable da'is for this language: "anyone" first, then each with their next free time. */
function DaaiChoice({ lang, gender, value, onChange }) {
  const { t, lang: ui, fmtDate, fmtTime } = useI18n();
  const [people, setPeople] = useState(null);
  useEffect(() => {
    setPeople(null);
    api.pGet(`/api/booking/daais?lang=${lang}&ui=${ui}`).then(setPeople).catch(() => setPeople([]));
  }, [lang, ui]);
  const shown = (people || []).filter((p) => !gender || p.gender === gender);
  useEffect(() => {
    if (value && people && !shown.some((p) => p.id === value)) onChange(null);
  }, [value, people, gender]); // eslint-disable-line react-hooks/exhaustive-deps
  if (!people) return <Spinner />;
  return (
    <div className="daai-pick" role="radiogroup" aria-label={t("book.who")}>
      <button type="button" role="radio" className="daai-option" aria-checked={!value} onClick={() => onChange(null)}>
        <strong>{t("book.anyone")}</strong><span className="small muted">{t("book.anyone_hint")}</span>
      </button>
      {shown.map((p) => (
        <button key={p.id} type="button" role="radio" className="daai-option" aria-checked={value === p.id} onClick={() => onChange(p.id)}>
          <strong>{p.name}</strong>
          <span className="small muted">
            {p.next_slot ? t("book.next", { when: `${fmtDate(p.next_slot, { weekday: "short", day: "numeric", month: "short" })} · ${fmtTime(p.next_slot)}` }) : t("book.full")}
            {p.city ? ` · ${p.city}` : ""}
          </span>
          {p.bio && <span className="small muted daai-bio">{p.bio}</span>}
        </button>
      ))}
    </div>
  );
}

function Booked({ booking, moved, onMine, onAgain }) {
  const { t, lang, fmtDate, fmtTime, fmtNum } = useI18n();
  return (
    <div className="card stack book-done">
      <div className="book-done-head"><span className="book-done-icon"><Icon name="check" size={26} /></span><h3>{t(moved ? "book.moved_title" : "book.done_title")}</h3></div>
      <dl className="book-summary">
        <dt>{t("book.with")}</dt><dd>{daaiName(booking.daai, lang)}</dd>
        <dt>{t("book.when")}</dt><dd>{fmtDate(booking.starts_at)} · {fmtTime(booking.starts_at)} – {fmtTime(booking.ends_at)}</dd>
        <dt>{t("book.zone")}</dt><dd>{zoneName(lang)}</dd>
        <dt>{t("book.length")}</dt><dd>{t("book.minutes", { n: fmtNum(booking.minutes) })}</dd>
      </dl>
      <p className="small muted">{t("book.done_hint")}</p>
      <CalendarButtons booking={booking} />
      <div className="row">
        <button type="button" className="btn btn-primary" onClick={onMine}><Icon name="calendar" />{t("book.my")}</button>
        <button type="button" className="btn" onClick={onAgain}>{t("book.another")}</button>
      </div>
    </div>
  );
}

export default function BookFlow({ query, initialDaai, initialLang, onMine }) {
  const { t, lang: ui, fmtDate, fmtTime, fmtNum, langName } = useI18n();
  const { account, loaded } = useAccount();
  const [lang, setLang] = useState(initialLang || query.lang || ui);
  const [gender, setGender] = useState("");
  const [daai, setDaai] = useState(initialDaai || (query.daai ? Number(query.daai) : null));
  const [minutes, setMinutes] = useState(query.minutes === "60" ? 60 : 30);
  const [slots, setSlots] = useState(null);
  const [failed, setFailed] = useState(null);
  const [day, setDay] = useState(null);
  const [slot, setSlot] = useState(query.slot || null);   // kept through sign-in (?slot=), like Calendly
  const [stale, setStale] = useState(false);              // the booking to move can no longer be moved
  const [note, setNote] = useState("");
  const [step, setStep] = useState("pick");     // pick | review
  const [busy, setBusy] = useState(false);
  const [booked, setBooked] = useState(null);
  const [mine, setMine] = useState(null);       // my bookings, to say up front when the limit is reached
  // Rescheduling (?reschedule=<id>): start from that booking's choices; it is replaced only once the new time is booked.
  const [moving, setMoving] = useState(null);
  const rescheduleId = query.reschedule ? Number(query.reschedule) : null;
  useEffect(() => {
    if (!rescheduleId) return;
    api.get(`/api/bookings/${rescheduleId}`).then((b) => {
      if (!b.can_cancel) { setStale(true); return; }
      setMoving(b);
      setLang(b.lang);
      setDaai(b.daai?.id || null);
      setMinutes(b.minutes);
      setNote(b.note || "");
    }).catch((err) => toast(errorText(err, t), "error"));
  }, [rescheduleId]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { if (account) api.get("/api/bookings").then(setMine).catch(() => {}); }, [account?.username]);
  const full = !moving && mine && mine.upcoming.length >= mine.max_upcoming;

  const load = async () => {
    const q = new URLSearchParams({ lang, minutes: String(minutes), gender });
    if (daai) q.set("daai_id", String(daai));
    if (moving) q.set("replaces", String(moving.id));
    try {
      const res = moving ? await api.get(`/api/booking/slots?${q}`) : await api.pGet(`/api/booking/slots?${q}`);
      setSlots(res.slots);
      setFailed(null);
    } catch (err) { setFailed(err); }
  };
  // A new choice clears the picked time (the first run keeps a time brought back from sign-in).
  const first = useRef(true);
  useEffect(() => {
    setSlots(null);
    if (first.current) { first.current = false; return; }
    setSlot(null);
  }, [lang, gender, daai, minutes, moving]);
  usePolling(load, 60000, [lang, gender, daai, minutes, moving], step === "pick" && !booked && !stale && (!rescheduleId || Boolean(moving)));

  const byDay = useMemo(() => {
    const out = {};
    for (const s of slots || []) (out[localDay(s.starts_at)] ||= []).push(s);
    return out;
  }, [slots]);
  const days = nextDays(DAYS);
  // Keep the chosen day if it still has times, else jump to the first day that has some.
  useEffect(() => {
    if (!slots) return;
    if (!day && slot && slots.some((s) => s.starts_at === slot)) setDay(localDay(slot));   // back from sign-in
    else if (!day || !byDay[day]) setDay(days.find((d) => byDay[d]) || null);
    if (slot && !slots.some((s) => s.starts_at === slot)) setSlot(null);
  }, [slots]); // eslint-disable-line react-hooks/exhaustive-deps

  const confirm = async () => {
    setBusy(true);
    try {
      const res = await api.post("/api/bookings", {
        starts_at: slot, minutes, lang, gender_pref: gender, daai_id: daai, note: note.trim(),
        referral_id: query.ref ? Number(query.ref) : null, replaces: moving ? moving.id : null,
      });
      setBooked(res);
      toast(t(moving ? "book.moved_toast" : "book.done_toast"), "success");
    } catch (err) {
      if (err.status === 409 && err.detail === "slot taken") {
        toast(t("book.taken"), "error");
        setStep("pick");
        setSlot(null);
        load();
      } else toast(errorText(err, t), "error");
    } finally { setBusy(false); }
  };

  if (booked) {
    return <Booked booking={booked} moved={Boolean(moving)} onMine={onMine} onAgain={() => { setBooked(null); setMoving(null); setStep("pick"); setSlot(null); setNote(""); }} />;
  }

  const signedOut = loaded && !account;
  // Signing in brings the seeker back to the same choices, the picked time and the referral card.
  const signInHref = () => {
    const q = new URLSearchParams({ mode: "book", lang });
    if (daai) q.set("daai", String(daai));
    if (minutes !== 30) q.set("minutes", String(minutes));
    if (slot) q.set("slot", slot);
    for (const k of ["ref", "card", "chat"]) if (query[k]) q.set(k, query[k]);
    return `#/account?next=${encodeURIComponent(`/talk?${q}`)}`;
  };

  if (stale) {
    return (
      <div className="card stack talk-card">
        <Notice kind="warn" icon="alert">{t("book.cant_move")}</Notice>
        <div className="row">
          <button type="button" className="btn btn-primary" onClick={onMine}><Icon name="calendar" />{t("book.my")}</button>
        </div>
      </div>
    );
  }

  if (step === "review") {
    const end = new Date(new Date(slot).getTime() + minutes * 60000).toISOString();
    return (
      <div className="card stack talk-card">
        <h3>{t("book.review")}</h3>
        {moving && <Notice kind="mint" icon="clock">{t("book.moving_from", { when: `${fmtDate(moving.starts_at)} · ${fmtTime(moving.starts_at)}` })}</Notice>}
        <dl className="book-summary">
          <dt>{t("book.with")}</dt><dd>{daai ? null : t("book.anyone")}<DaaiLabel id={daai} lang={lang} /></dd>
          <dt>{t("book.when")}</dt><dd>{fmtDate(slot)} · {fmtTime(slot)} – {fmtTime(end)}</dd>
          <dt>{t("book.zone")}</dt><dd>{zoneName(ui)}</dd>
          <dt>{t("book.length")}</dt><dd>{t("book.minutes", { n: fmtNum(minutes) })}</dd>
          <dt>{t("book.lang")}</dt><dd>{langName(lang)}</dd>
        </dl>
        <div className="field">
          <label htmlFor="book-note">{t("book.note")} <span className="faint">({t("common.optional")})</span></label>
          <textarea id="book-note" className="textarea" rows={3} maxLength={300} value={note} onChange={(e) => setNote(e.target.value)} placeholder={t("book.note_ph")} />
          <span className="small faint">{t("book.note_hint")}</span>
        </div>
        {query.card && <Notice kind="mint" icon="check">{t("talk.with_card")}</Notice>}
        <p className="small muted"><Icon name="shield" size={16} /> {t("book.rules")}</p>
        <div className="row">
          <button type="button" className="btn btn-primary btn-lg" disabled={busy} onClick={confirm}><Icon name="check" />{t(busy ? "book.booking" : moving ? "book.confirm_move" : "book.confirm")}</button>
          <button type="button" className="btn" disabled={busy} onClick={() => setStep("pick")}>{t("common.back")}</button>
        </div>
      </div>
    );
  }

  const daySlots = (day && byDay[day]) || [];
  // Moving to the very same time, length and da'i would change nothing.
  const sameAsNow = moving && slot === moving.starts_at && minutes === moving.minutes && (!daai || daai === moving.daai?.id);
  const groups = ["morning", "afternoon", "evening"].map((p) => [p, daySlots.filter((s) => period(s.starts_at) === p)]).filter(([, l]) => l.length);
  return (
    <div className="card stack talk-card">
      {moving && (
        <Notice kind="mint" icon="clock">
          <div className="stack">
            <span>{t("book.moving", { when: `${fmtDate(moving.starts_at)} · ${fmtTime(moving.starts_at)}` })}</span>
            <div className="row"><button type="button" className="btn btn-sm" onClick={onMine}>{t("book.keep_time")}</button></div>
          </div>
        </Notice>
      )}
      {full && (
        <Notice kind="warn" icon="alert">
          <div className="stack">
            <span>{t("book.max", { n: fmtNum(mine.max_upcoming) })}</span>
            <div className="row"><button type="button" className="btn btn-sm" onClick={onMine}>{t("book.my")}</button></div>
          </div>
        </Notice>
      )}
      {signedOut && (
        <Notice kind="warn" icon="lock">
          <div className="stack">
            <span>{t("book.need_account")}</span>
            <div className="row">
              <a className="btn btn-primary btn-sm" href={signInHref()}>{t("acc.signin_btn")}</a>
            </div>
          </div>
        </Notice>
      )}
      <h3>{t("talk.lang")}</h3>
      <div className="tabs tabs-fit" role="radiogroup" aria-label={t("talk.lang")}>
        {LANGS.map((code) => <button key={code} type="button" role="radio" aria-checked={lang === code} onClick={() => setLang(code)}>{langName(code)}</button>)}
      </div>
      <h3>{t("talk.gender")}</h3>
      <div className="tabs tabs-fit" role="radiogroup" aria-label={t("talk.gender")}>
        {[["", "talk.any"], ["m", "talk.male"], ["f", "talk.female"]].map(([v, k]) => (
          <button key={v || "any"} type="button" role="radio" aria-checked={gender === v} onClick={() => setGender(v)}>{t(k)}</button>
        ))}
      </div>
      <h3>{t("book.who")}</h3>
      <DaaiChoice lang={lang} gender={gender} value={daai} onChange={setDaai} />
      <h3>{t("book.length")}</h3>
      <div className="tabs tabs-fit" role="radiogroup" aria-label={t("book.length")}>
        {[30, 60].map((m) => <button key={m} type="button" role="radio" aria-checked={minutes === m} onClick={() => setMinutes(m)}>{t("book.minutes", { n: fmtNum(m) })}</button>)}
      </div>
      {minutes === 60 && <p className="small muted">{t("book.sixty_hint")}</p>}

      <div className="row spread">
        <h3>{t("book.pick_day")}</h3>
        <span className="small faint"><Icon name="globe" size={14} /> {t("book.zone_note", { zone: zoneName(ui) })}</span>
      </div>
      {!slots ? (failed ? <Notice kind="warn" icon="alert">{errorText(failed, t)}</Notice> : <Spinner />) : !slots.length ? (
        <div className="empty"><Icon name="calendar" /><p>{t("book.none")}</p></div>
      ) : (
        <>
          <div className="day-strip" role="radiogroup" aria-label={t("book.pick_day")}>
            {days.map((d, i) => {
              const n = (byDay[d] || []).length;
              return (
                <button key={d} type="button" role="radio" className="day-chip" aria-checked={day === d} disabled={!n} onClick={() => { setDay(d); setSlot(null); }}>
                  <span className="day-chip-wd">{i === 0 ? t("book.today") : i === 1 ? t("book.tomorrow") : fmtDate(dayIso(d), { weekday: "short" })}</span>
                  <strong>{fmtDate(dayIso(d), { day: "numeric" })}</strong>
                  <span className="day-chip-mo">{fmtDate(dayIso(d), { month: "short" })}</span>
                </button>
              );
            })}
          </div>
          {day && <h4 className="book-day-title">{fmtDate(dayIso(day))}</h4>}
          {groups.map(([p, list]) => (
            <div key={p} className="stack slot-group">
              <span className="small faint">{t(`book.${p}`)}</span>
              <div className="slot-grid" role="radiogroup" aria-label={t(`book.${p}`)}>
                {list.map((s) => (
                  <button key={s.starts_at} type="button" role="radio" className="slot-chip" aria-checked={slot === s.starts_at} onClick={() => setSlot(s.starts_at)}>
                    {fmtTime(s.starts_at)}
                    {moving && moving.starts_at === s.starts_at && <span className="slot-now">{t("book.current")}</span>}
                  </button>
                ))}
              </div>
            </div>
          ))}
        </>
      )}
      <div className="row">
        {signedOut ? (
          <a className={`btn btn-primary btn-lg${slot ? "" : " is-disabled"}`} href={slot ? signInHref() : undefined} aria-disabled={!slot}>
            <Icon name="lock" />{t("book.signin_continue")}
          </a>
        ) : (
          <button type="button" className="btn btn-primary btn-lg" disabled={!slot || full || sameAsNow} onClick={() => setStep("review")}>
            <Icon name="calendar" />{t("common.continue")}
          </button>
        )}
        {slot && <span className="small muted">{fmtDate(slot, { weekday: "long", day: "numeric", month: "long" })} · {fmtTime(slot)}</span>}
      </div>
      <p className="faint">{t("book.lead")}</p>
    </div>
  );
}

/** A da'i's name from the booking directory (loaded once per language). */
function DaaiLabel({ id, lang }) {
  const { lang: ui } = useI18n();
  const [name, setName] = useState("");
  useEffect(() => {
    if (!id) return;
    api.pGet(`/api/booking/daais?lang=${lang}&ui=${ui}`).then((list) => setName(list.find((p) => p.id === id)?.name || "")).catch(() => {});
  }, [id, lang, ui]);
  return id ? name : null;
}
