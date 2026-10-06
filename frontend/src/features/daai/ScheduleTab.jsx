// Da'i console, "My schedule" tab: weekly hours for booked calls (in the da'i's own time zone), days off,
// pausing bookings, and the list of upcoming and past bookings. Owner: Eman. Mounted by DaaiConsole.jsx.
import "./strings.js";
import "./daai.css";
import { useEffect, useMemo, useState } from "react";
import { api } from "../../core/api.js";
import { useI18n } from "../../core/i18n.jsx";
import { Icon, Notice, Spinner, errorText, openSheet, toast, usePolling } from "../../core/ui.jsx";
import { LoadError } from "./bits.jsx";

const WEEK = ["sun", "mon", "tue", "wed", "thu", "fri", "sat"];   // the week as it is laid out in the region
const TIMES = Array.from({ length: 49 }, (_, i) => `${String(Math.floor(i / 2)).padStart(2, "0")}:${i % 2 ? "30" : "00"}`);
const DEFAULT_RANGE = ["17:00", "21:00"];

function zones() {
  try { return Intl.supportedValuesOf("timeZone"); } catch { return ["Asia/Riyadh", "Africa/Cairo", "Europe/London", "America/New_York", "Asia/Jakarta", "UTC"]; }
}
const browserZone = () => { try { return Intl.DateTimeFormat().resolvedOptions().timeZone || "Asia/Riyadh"; } catch { return "Asia/Riyadh"; } };

/** "18:30" shown in the UI language's clock (6:30 PM, ٦:٣٠ م). */
function useClockLabel() {
  const { lang } = useI18n();
  return useMemo(() => {
    const f = new Intl.DateTimeFormat(lang === "ar" ? "ar-SA-u-nu-arab" : "en-GB", { hour: "numeric", minute: "2-digit", hour12: true, timeZone: "UTC" });
    return (hhmm) => (hhmm === "24:00" ? f.format(Date.UTC(2000, 0, 2, 0, 0)) : f.format(Date.UTC(2000, 0, 1, ...hhmm.split(":").map(Number))));
  }, [lang]);
}

function TimeSelect({ value, onChange, from = 0, to = 48, label }) {
  const clock = useClockLabel();
  return (
    <select className="select sched-time" aria-label={label} value={value} onChange={(e) => onChange(e.target.value)}>
      {TIMES.slice(from, to + 1).map((x) => <option key={x} value={x}>{clock(x)}</option>)}
    </select>
  );
}

function WeekEditor({ weekly, onChange }) {
  const { t } = useI18n();
  const dayName = (d) => t(`ds.day_${d}`);
  const set = (day, ranges) => onChange({ ...weekly, [day]: ranges });
  const copyToAll = (day) => onChange(Object.fromEntries(WEEK.map((d) => [d, (weekly[day] || []).map((r) => [...r])])));
  return (
    <div className="sched-week">
      {WEEK.map((day) => {
        const ranges = weekly[day] || [];
        const on = ranges.length > 0;
        return (
          <div className={`sched-day${on ? " is-on" : ""}`} key={day}>
            <label className="check sched-day-name">
              <input type="checkbox" checked={on} onChange={(e) => set(day, e.target.checked ? [[...DEFAULT_RANGE]] : [])} />
              <span>{dayName(day)}</span>
            </label>
            <div className="stack sched-ranges">
              {!on && <span className="faint small">{t("ds.closed")}</span>}
              {ranges.map((r, i) => {
                const fromIdx = TIMES.indexOf(r[0]);
                return (
                  <div className="row sched-range" key={i}>
                    <TimeSelect label={t("ds.from")} value={r[0]} to={47} onChange={(v) => {
                      const next = ranges.map((x) => [...x]);
                      next[i][0] = v;
                      if (next[i][1] <= v) next[i][1] = TIMES[Math.min(48, TIMES.indexOf(v) + 2)];
                      set(day, next);
                    }} />
                    <span className="faint">–</span>
                    <TimeSelect label={t("ds.to")} value={r[1]} from={fromIdx + 1} onChange={(v) => {
                      const next = ranges.map((x) => [...x]);
                      next[i][1] = v;
                      set(day, next);
                    }} />
                    <button type="button" className="icon-btn" aria-label={t("ds.remove")} title={t("ds.remove")} onClick={() => set(day, ranges.filter((_, j) => j !== i))}><Icon name="x" size={16} /></button>
                  </div>
                );
              })}
            </div>
            <div className="row sched-day-actions">
              {on && ranges.length < 6 && (
                <button type="button" className="btn btn-ghost btn-sm" onClick={() => {
                  const last = ranges[ranges.length - 1][1];
                  const start = last === "24:00" ? "08:00" : last;
                  set(day, [...ranges, [start, TIMES[Math.min(48, TIMES.indexOf(start) + 2)]]]);
                }}><Icon name="plus" />{t("ds.add")}</button>
              )}
              {on && <button type="button" className="btn btn-ghost btn-sm" onClick={() => copyToAll(day)}>{t("ds.copy_all")}</button>}
            </div>
          </div>
        );
      })}
    </div>
  );
}

/** Checks a week before it is sent: each range ends after it starts and no two ranges of a day overlap. */
function weekProblem(weekly) {
  for (const day of WEEK) {
    const r = [...(weekly[day] || [])].sort((a, b) => (a[0] < b[0] ? -1 : 1));
    for (let i = 0; i < r.length; i += 1) {
      if (r[i][0] >= r[i][1]) return "ds.err_order";
      if (i && r[i - 1][1] > r[i][0]) return "ds.err_overlap";
    }
  }
  return null;
}

function CancelSheet({ booking, close, onDone }) {
  const { t } = useI18n();
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      await api.dPost(`/api/daai/bookings/${booking.id}/cancel`, { note: note.trim() });
      toast(t("ds.cancelled"), "success");
      onDone();
      close();
    } catch (err) { toast(errorText(err, t), "error"); setBusy(false); }
  };
  return (
    <form className="stack" onSubmit={submit}>
      <p>{t("ds.cancel_lead")}</p>
      <div className="field">
        <label htmlFor="ds-cancel-note">{t("ds.cancel_note")} <span className="faint">({t("common.optional")})</span></label>
        <textarea id="ds-cancel-note" className="textarea" rows={3} maxLength={300} value={note} onChange={(e) => setNote(e.target.value)} placeholder={t("ds.cancel_ph")} />
      </div>
      <div className="row">
        <button type="submit" className="btn btn-danger" disabled={busy}>{t("ds.cancel_yes")}</button>
        <button type="button" className="btn btn-ghost" disabled={busy} onClick={close}>{t("ds.keep")}</button>
      </div>
    </form>
  );
}

function statusLabel(b, t) {
  if (b.status === "done") return t("ds.st_done");
  if (b.status === "missed") return t(b.missed_by === "daai" ? "ds.st_missed_you" : "ds.st_missed_seeker");
  if (b.status === "cancelled") return t(b.cancelled_by === "daai" ? "ds.st_cancel_you" : "ds.st_cancel_seeker");
  return t("ds.st_booked");
}

function BookingRow({ b, onChanged }) {
  const { t, langName, fmtDate, fmtTime, fmtNum } = useI18n();
  const live = b.status === "booked";
  return (
    <div className="queue-item sched-booking">
      <div className="stack" style={{ gap: 2 }}>
        <strong>{fmtDate(b.starts_at, { weekday: "long", day: "numeric", month: "long" })} · {fmtTime(b.starts_at)} – {fmtTime(b.ends_at)}</strong>
        <span className="small muted">{langName(b.lang)} · {t("ds.minutes", { n: fmtNum(b.minutes) })}{b.note ? " · " : ""}{b.note && <span dir="auto">{b.note}</span>}</span>
      </div>
      <div className="row">
        {b.has_card && <span className="badge badge-mint">{t("dc.card")}</span>}
        {b.has_chat && <span className="badge badge-mint">{t("dc.chat_badge")}</span>}
        <span className={`badge ${live ? "badge-purple" : b.status === "done" ? "badge-mint" : "badge-warn"}`}>{statusLabel(b, t)}</span>
        {live && b.can_cancel && (
          <button type="button" className="btn btn-sm btn-danger-soft"
            onClick={() => openSheet({ title: t("ds.cancel_title"), render: (close) => <CancelSheet booking={b} close={close} onDone={onChanged} /> })}>
            {t("ds.cancel")}
          </button>
        )}
      </div>
    </div>
  );
}

function Bookings({ data, onChanged }) {
  const { t, fmtNum } = useI18n();
  const [showPast, setShowPast] = useState(false);
  return (
    <section className="card stack">
      <h3>{t("ds.upcoming")} {data.upcoming.length > 0 && <span className="faint">({fmtNum(data.upcoming.length)})</span>}</h3>
      <p className="small muted"><Icon name="shield" size={16} /> {t("ds.privacy")}</p>
      {data.upcoming.length === 0
        ? <div className="empty"><Icon name="calendar" /><p>{t("ds.none")}</p></div>
        : data.upcoming.map((b) => <BookingRow key={b.id} b={b} onChanged={onChanged} />)}
      {data.past.length > 0 && (
        <>
          <button type="button" className="btn btn-ghost btn-sm" style={{ alignSelf: "flex-start" }} aria-expanded={showPast} onClick={() => setShowPast(!showPast)}>
            {t("ds.past")} ({fmtNum(data.past.length)})
          </button>
          {showPast && data.past.map((b) => <BookingRow key={b.id} b={b} onChanged={onChanged} />)}
        </>
      )}
    </section>
  );
}

function ScheduleTab() {
  const { t, fmtDate, fmtNum } = useI18n();
  const [saved, setSaved] = useState(null);
  const [draft, setDraft] = useState(null);
  const [failed, setFailed] = useState(null);
  const [busy, setBusy] = useState(false);
  const [bookings, setBookings] = useState(null);
  const [offDay, setOffDay] = useState("");

  const load = async () => {
    try {
      const s = await api.dGet("/api/daai/schedule");
      const start = s.set ? s : { ...s, tz: browserZone() };
      setSaved(start);
      setDraft({ tz: start.tz, weekly: start.weekly, days_off: start.days_off, paused: start.paused });
      setFailed(null);
    } catch (err) { setFailed(err); }
  };
  useEffect(() => { load(); }, []);
  const loadBookings = async () => setBookings(await api.dGet("/api/daai/bookings"));
  usePolling(loadBookings, 30000);

  if (!draft) return failed ? <LoadError err={failed} onRetry={load} /> : <Spinner />;
  const changed = JSON.stringify(draft) !== JSON.stringify({ tz: saved.tz, weekly: saved.weekly, days_off: saved.days_off, paused: saved.paused });
  const problem = weekProblem(draft.weekly);
  const hasHours = WEEK.some((d) => (draft.weekly[d] || []).length);

  const save = async (next = draft, keepEdits = false) => {
    setBusy(true);
    try {
      const s = await api.dPost("/api/daai/schedule", next);
      setSaved(s);
      setDraft(keepEdits ? { ...draft, paused: s.paused } : { tz: s.tz, weekly: s.weekly, days_off: s.days_off, paused: s.paused });
      toast(t("ds.saved"), "success");
    } catch (err) { toast(errorText(err, t), "error"); }
    setBusy(false);
  };
  // Pausing is a switch: it saves at once, like the "available" switch, and keeps any unsaved edits to the hours.
  const setTaking = (e) => save({ tz: saved.tz, weekly: saved.weekly, days_off: saved.days_off, paused: !e.target.checked }, true);
  const addOff = () => {
    if (!offDay || draft.days_off.includes(offDay)) return;
    setDraft({ ...draft, days_off: [...draft.days_off, offDay].sort() });
    setOffDay("");
  };
  // Bookings on a day being taken off are listed so the da'i cancels them on purpose; days off never cancel anything.
  const clashes = (bookings?.upcoming || []).filter((b) => draft.days_off.some((d) => {
    const s = new Date(b.starts_at);
    return d === `${s.getFullYear()}-${String(s.getMonth() + 1).padStart(2, "0")}-${String(s.getDate()).padStart(2, "0")}`;
  }));
  const today = new Date().toISOString().slice(0, 10);
  const dayIso = (d) => new Date(`${d}T12:00:00`).toISOString();

  return (
    <div className="stack">
      <section className="card stack">
        <div className="row spread">
          <div>
            <h3>{t("ds.title")}</h3>
            <p className="small muted">{t("ds.lead")}</p>
          </div>
          <label className={`row${busy ? " daai-busy" : ""}`}>
            <span className="switch"><input type="checkbox" checked={!saved.paused} disabled={busy || !saved.set} onChange={setTaking} /><span /></span>
            <span>{t("ds.taking")}</span>
          </label>
        </div>
        {saved.paused && <Notice kind="warn" icon="alert">{t("ds.paused_note")}</Notice>}
        {!saved.set && <Notice icon="info">{t("ds.first_time")}</Notice>}
        <div className="field">
          <label htmlFor="ds-tz">{t("ds.tz")}</label>
          <select id="ds-tz" className="select" value={draft.tz} onChange={(e) => setDraft({ ...draft, tz: e.target.value })}>
            {zones().map((z) => <option key={z} value={z}>{z.replace(/_/g, " ")}</option>)}
          </select>
          <span className="small faint">{t("ds.tz_hint")}</span>
        </div>
        <p className="small muted"><Icon name="clock" size={16} /> {t("ds.slots_note")}</p>
        <WeekEditor weekly={draft.weekly} onChange={(weekly) => setDraft({ ...draft, weekly })} />

        <h4>{t("ds.days_off")}</h4>
        <p className="small muted">{t("ds.days_off_hint")}</p>
        <div className="row">
          <input type="date" className="input sched-date" min={today} value={offDay} aria-label={t("ds.days_off")} onChange={(e) => setOffDay(e.target.value)} />
          <button type="button" className="btn btn-sm" disabled={!offDay} onClick={addOff}><Icon name="plus" />{t("ds.add_off")}</button>
        </div>
        {draft.days_off.length > 0 && (
          <div className="row">
            {draft.days_off.map((d) => (
              <span className="chip" key={d}>
                {fmtDate(dayIso(d), { weekday: "short", day: "numeric", month: "short" })}
                <button type="button" className="icon-btn" aria-label={t("ds.remove")} onClick={() => setDraft({ ...draft, days_off: draft.days_off.filter((x) => x !== d) })}><Icon name="x" size={14} /></button>
              </span>
            ))}
          </div>
        )}
        {clashes.length > 0 && <Notice kind="warn" icon="alert">{t("ds.clash", { n: fmtNum(clashes.length) })}</Notice>}

        {problem && <Notice kind="warn" icon="alert">{t(problem)}</Notice>}
        <div className="row">
          <button type="button" className="btn btn-primary" disabled={busy || !changed || Boolean(problem)} onClick={() => save()}>{t(busy ? "ds.saving" : "ds.save")}</button>
          {changed && <button type="button" className="btn btn-ghost" disabled={busy} onClick={() => setDraft({ tz: saved.tz, weekly: saved.weekly, days_off: saved.days_off, paused: saved.paused })}>{t("ds.discard")}</button>}
          {!hasHours && <span className="small faint">{t("ds.no_hours")}</span>}
        </div>
      </section>
      {bookings ? <Bookings data={bookings} onChanged={loadBookings} /> : <Spinner />}
    </div>
  );
}

export const scheduleTab = { key: "schedule", labelKey: "ds.tab", component: ScheduleTab, daaiOnly: true };   // reviewers take no bookings
