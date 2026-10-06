// Talk page, "Book a time" (seeker): pick a language, a da'i (or anyone), a length, a day and a free time,
// review, confirm. Times show in the viewer's own time zone. Owner: Eman (calls).
import "./strings.js";
import "./calls.css";
import { useEffect, useMemo, useState } from "react";
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

function Booked({ booking, onMine, onAgain }) {
  const { t, lang, fmtDate, fmtTime, fmtNum } = useI18n();
  return (
    <div className="card stack book-done">
      <div className="book-done-head"><span className="book-done-icon"><Icon name="check" size={26} /></span><h3>{t("book.done_title")}</h3></div>
      <dl className="book-summary">
        <dt>{t("book.with")}</dt><dd>{daaiName(booking.daai, lang)}</dd>
        <dt>{t("book.when")}</dt><dd>{fmtDate(booking.starts_at)} · {fmtTime(booking.starts_at)} – {fmtTime(booking.ends_at)}</dd>
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
  const [daai, setDaai] = useState(initialDaai || null);
  const [minutes, setMinutes] = useState(30);
  const [slots, setSlots] = useState(null);
  const [failed, setFailed] = useState(null);
  const [day, setDay] = useState(null);
  const [slot, setSlot] = useState(null);
  const [note, setNote] = useState("");
  const [step, setStep] = useState("pick");     // pick | review
  const [busy, setBusy] = useState(false);
  const [booked, setBooked] = useState(null);

  const load = async () => {
    const q = new URLSearchParams({ lang, minutes: String(minutes), gender });
    if (daai) q.set("daai_id", String(daai));
    try { setSlots((await api.pGet(`/api/booking/slots?${q}`)).slots); setFailed(null); } catch (err) { setFailed(err); }
  };
  useEffect(() => { setSlots(null); setSlot(null); }, [lang, gender, daai, minutes]);
  usePolling(load, 60000, [lang, gender, daai, minutes], step === "pick" && !booked);

  const byDay = useMemo(() => {
    const out = {};
    for (const s of slots || []) (out[localDay(s.starts_at)] ||= []).push(s);
    return out;
  }, [slots]);
  const days = nextDays(DAYS);
  // Keep the chosen day if it still has times, else jump to the first day that has some.
  useEffect(() => {
    if (!slots) return;
    if (!day || !byDay[day]) setDay(days.find((d) => byDay[d]) || null);
    if (slot && !slots.some((s) => s.starts_at === slot)) setSlot(null);
  }, [slots]); // eslint-disable-line react-hooks/exhaustive-deps

  const confirm = async () => {
    setBusy(true);
    try {
      const res = await api.post("/api/bookings", {
        starts_at: slot, minutes, lang, gender_pref: gender, daai_id: daai, note: note.trim(),
        referral_id: query.ref ? Number(query.ref) : null,
      });
      setBooked(res);
      toast(t("book.done_toast"), "success");
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
    return <Booked booking={booked} onMine={onMine} onAgain={() => { setBooked(null); setStep("pick"); setSlot(null); setNote(""); load(); }} />;
  }

  const signedOut = loaded && !account;
  const next = encodeURIComponent("/talk?mode=book");

  if (step === "review") {
    const end = new Date(new Date(slot).getTime() + minutes * 60000).toISOString();
    return (
      <div className="card stack talk-card">
        <h3>{t("book.review")}</h3>
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
          <button type="button" className="btn btn-primary btn-lg" disabled={busy} onClick={confirm}><Icon name="check" />{t(busy ? "book.booking" : "book.confirm")}</button>
          <button type="button" className="btn" disabled={busy} onClick={() => setStep("pick")}>{t("common.back")}</button>
        </div>
      </div>
    );
  }

  const daySlots = (day && byDay[day]) || [];
  const groups = ["morning", "afternoon", "evening"].map((p) => [p, daySlots.filter((s) => period(s.starts_at) === p)]).filter(([, l]) => l.length);
  return (
    <div className="card stack talk-card">
      {signedOut && (
        <Notice kind="warn" icon="lock">
          <div className="stack">
            <span>{t("book.need_account")}</span>
            <div className="row">
              <a className="btn btn-primary btn-sm" href={`#/account?next=${next}`}>{t("acc.signin_btn")}</a>
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
            {days.map((d) => {
              const n = (byDay[d] || []).length;
              return (
                <button key={d} type="button" role="radio" className="day-chip" aria-checked={day === d} disabled={!n} onClick={() => { setDay(d); setSlot(null); }}>
                  <span className="day-chip-wd">{fmtDate(dayIso(d), { weekday: "short" })}</span>
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
                  </button>
                ))}
              </div>
            </div>
          ))}
        </>
      )}
      <div className="row">
        <button type="button" className="btn btn-primary btn-lg" disabled={!slot || signedOut} onClick={() => setStep("review")}>
          <Icon name="calendar" />{t("common.continue")}
        </button>
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
