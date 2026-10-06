// Talk page, "My bookings" (seeker): upcoming and past booked calls, add to calendar, cancel, and the waiting
// room a booking opens 5 minutes before its start. Owner: Eman (calls).
import "./strings.js";
import "./calls.css";
import { useState } from "react";
import { api } from "../../core/api.js";
import { useI18n } from "../../core/i18n.jsx";
import { Icon, Notice, Spinner, errorText, toast, usePolling } from "../../core/ui.jsx";
import { useAccount } from "../account/public.js";
import { downloadIcs, googleCalendarUrl, zoneName } from "./bookingUtils.js";

export const daaiName = (d, lang) => (d ? (lang === "ar" ? d.name : d.name_en || d.name) : "");

/** "Add to calendar": Google Calendar, or an .ics file for Apple, Outlook and others. The calendar does the reminding. */
export function CalendarButtons({ booking }) {
  const { t, lang } = useI18n();
  const title = t("book.cal_title", { name: daaiName(booking.daai, lang) });
  const details = t("book.cal_details");
  return (
    <div className="row cal-buttons">
      <span className="small muted">{t("book.add_cal")}</span>
      <a className="btn btn-sm" href={googleCalendarUrl(booking, title, details)} target="_blank" rel="noopener noreferrer"><Icon name="calendar" />Google</a>
      <button type="button" className="btn btn-sm" onClick={() => downloadIcs(booking, title, details)}><Icon name="calendar" />{t("book.ics")}</button>
    </div>
  );
}

function statusText(b, t) {
  if (b.status === "done") return t("book.st_done");
  if (b.status === "missed") return t(b.missed_by === "daai" ? "book.st_missed_daai" : b.missed_by === "both" ? "book.st_missed_both" : "book.st_missed_you");
  if (b.status === "cancelled" && b.rescheduled_to) return t("book.st_moved");
  if (b.status === "cancelled") return t(b.cancelled_by === "seeker" ? "book.st_cancel_you" : b.cancelled_by === "daai" ? "book.st_cancel_daai" : "book.st_cancel_system");
  return t("book.st_booked");
}

function BookingItem({ b, onJoin, onChanged, onBookAgain, onReschedule }) {
  const { t, lang, fmtDate, fmtTime, fmtNum } = useI18n();
  const [asking, setAsking] = useState(false);
  const [busy, setBusy] = useState(false);
  const cancel = async () => {
    setBusy(true);
    try { await api.post(`/api/bookings/${b.id}/cancel`, {}); toast(t("book.cancelled"), "success"); onChanged(); } catch (err) { toast(errorText(err, t), "error"); }
    setBusy(false);
    setAsking(false);
  };
  const live = b.status === "booked";
  const bad = (b.status === "cancelled" && !b.rescheduled_to) || b.status === "missed";
  return (
    <article className={`booking-item${live ? " is-live" : ""}`}>
      <div className="booking-date" aria-hidden="true">
        <span>{fmtDate(b.starts_at, { weekday: "short" })}</span>
        <strong>{fmtDate(b.starts_at, { day: "numeric" })}</strong>
        <span>{fmtDate(b.starts_at, { month: "short" })}</span>
      </div>
      <div className="stack booking-body">
        <div className="row spread">
          <strong>{fmtTime(b.starts_at)} – {fmtTime(b.ends_at)}</strong>
          <span className={`badge ${live ? "badge-mint" : bad ? "badge-warn" : ""}`}>{statusText(b, t)}</span>
        </div>
        <span className="small muted">
          {t("book.with_name", { name: daaiName(b.daai, lang) })} · {t("book.minutes", { n: fmtNum(b.minutes) })} · {fmtDate(b.starts_at, { weekday: "long", day: "numeric", month: "long" })}
        </span>
        {b.note && <span className="small faint" dir="auto">{t("book.topic")}: {b.note}</span>}
        {b.cancel_note && <span className="small" dir="auto">{t("book.daai_said")}: {b.cancel_note}</span>}
        {live && (
          <div className="row">
            {b.can_join
              ? <button type="button" className="btn btn-primary btn-sm" onClick={() => onJoin(b.id)}><Icon name="talk" />{t("book.join")}</button>
              : <span className="small faint"><Icon name="clock" size={14} /> {t("book.join_at", { time: fmtTime(b.join_opens_at) })}</span>}
            {b.can_cancel && (asking ? (
              <span className="row daai-ask" role="group" aria-label={t("book.cancel_q")}>
                <span className="small">{t("book.cancel_q")}</span>
                <button type="button" className="btn btn-sm btn-danger" disabled={busy} onClick={cancel}>{t("book.cancel_yes")}</button>
                <button type="button" className="btn btn-sm btn-ghost" autoFocus disabled={busy} onClick={() => setAsking(false)}>{t("book.keep")}</button>
              </span>
            ) : <>
              <button type="button" className="btn btn-sm" onClick={() => onReschedule(b.id)}><Icon name="edit" />{t("book.reschedule")}</button>
              <button type="button" className="btn btn-sm btn-danger-soft" onClick={() => setAsking(true)}>{t("book.cancel")}</button>
            </>)}
          </div>
        )}
        {live && !b.can_join && <CalendarButtons booking={b} />}
        {bad && b.daai && <div className="row"><button type="button" className="btn btn-sm" onClick={() => onBookAgain(b.daai.id, b.lang)}><Icon name="calendar" />{t("book.again")}</button></div>}
      </div>
    </article>
  );
}

export default function MyBookings({ onJoin, onBook, onBookAgain, onReschedule }) {
  const { t, fmtNum, lang } = useI18n();
  const { account, loaded } = useAccount();
  const [data, setData] = useState(null);
  const [failed, setFailed] = useState(null);
  const [showPast, setShowPast] = useState(false);
  const load = async () => {
    try { setData(await api.get("/api/bookings")); setFailed(null); } catch (err) { setFailed(err); }
  };
  usePolling(load, 20000, [account?.username], Boolean(account));
  if (loaded && !account) {
    return (
      <div className="card stack center">
        <Icon name="lock" size={32} />
        <p>{t("book.need_account")}</p>
        <div className="row" style={{ justifyContent: "center" }}><a className="btn btn-primary" href={`#/account?next=${encodeURIComponent("/talk?mode=bookings")}`}>{t("acc.signin_btn")}</a></div>
      </div>
    );
  }
  if (!data) return failed ? <Notice kind="warn" icon="alert">{errorText(failed, t)}</Notice> : <Spinner />;
  return (
    <div className="stack">
      <section className="card stack">
        <div className="row spread">
          <h3>{t("book.upcoming")} {data.upcoming.length > 0 && <span className="faint">({fmtNum(data.upcoming.length)})</span>}</h3>
          {data.upcoming.length < data.max_upcoming && <button type="button" className="btn btn-sm btn-primary" onClick={onBook}><Icon name="plus" />{t("book.new")}</button>}
        </div>
        {data.upcoming.length === 0 ? (
          <div className="empty"><Icon name="calendar" /><p>{t("book.empty")}</p></div>
        ) : data.upcoming.map((b) => <BookingItem key={b.id} b={b} onJoin={onJoin} onChanged={load} onBookAgain={onBookAgain} onReschedule={onReschedule} />)}
        {data.upcoming.length >= data.max_upcoming && <p className="small muted">{t("book.max", { n: fmtNum(data.max_upcoming) })}</p>}
        <p className="small faint"><Icon name="globe" size={14} /> {t("book.zone_note", { zone: zoneName(lang) })}</p>
      </section>
      {data.past.length > 0 && (
        <section className="card stack">
          <button type="button" className="btn btn-ghost btn-sm past-toggle" aria-expanded={showPast} onClick={() => setShowPast(!showPast)}>
            {t("book.past")} ({fmtNum(data.past.length)})
          </button>
          {showPast && data.past.map((b) => <BookingItem key={b.id} b={b} onJoin={onJoin} onChanged={load} onBookAgain={onBookAgain} onReschedule={onReschedule} />)}
        </section>
      )}
    </div>
  );
}

/** The booking's waiting room: tells the server the seeker is here, then waits for the da'i to press Start. */
export function BookingRoom({ id, onCall, onLeave, onCallNow, onBookAgain }) {
  const { t, lang, fmtTime, fmtDate } = useI18n();
  const [b, setB] = useState(null);
  const [failed, setFailed] = useState(null);
  usePolling(async () => {
    try {
      let cur = await api.get(`/api/bookings/${id}`);
      if (cur.status === "booked" && cur.can_join && !cur.ready) cur = await api.post(`/api/bookings/${id}/join`, {});
      setB(cur);
      setFailed(null);
      if (cur.call_id) onCall(cur.call_id);
    } catch (err) { setFailed(err); }
  }, 3000, [id], true, { background: true });
  if (!b) return failed ? <Notice kind="warn" icon="alert">{errorText(failed, t)}</Notice> : <Spinner />;
  const name = daaiName(b.daai, lang);
  if (b.status !== "booked") {
    return (
      <div className="card stack">
        <p>{b.status === "missed" && b.missed_by === "daai" ? t("book.room_missed") : statusText(b, t)}</p>
        <div className="row">
          <button type="button" className="btn btn-primary" onClick={onCallNow}><Icon name="talk" />{t("talk.call")}</button>
          {b.daai && <button type="button" className="btn" onClick={() => onBookAgain(b.daai.id, b.lang)}><Icon name="calendar" />{t("book.again")}</button>}
          <button type="button" className="btn btn-ghost" onClick={onLeave}>{t("book.my")}</button>
        </div>
      </div>
    );
  }
  const early = !b.can_join;
  return (
    <div className="card stack center waiting">
      <div className="pulse"><Icon name="calendar" size={40} /></div>
      <h3>{early ? t("book.room_early", { time: fmtTime(b.join_opens_at) }) : t("book.room_wait", { name })}</h3>
      <p className="muted">{fmtDate(b.starts_at)} · {fmtTime(b.starts_at)} – {fmtTime(b.ends_at)}</p>
      <p className="small faint">{t("book.room_hint")}</p>
      <div className="row" style={{ justifyContent: "center" }}><button type="button" className="btn" onClick={onLeave}>{t("common.back")}</button></div>
    </div>
  );
}
