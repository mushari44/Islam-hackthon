// Group and meetup cards, used on the community lists and under My activities. Owner: Mushari (community).
import { useState } from "react";
import { api, apiUrl } from "../../core/api.js";
import { useI18n } from "../../core/i18n.jsx";
import { navigate } from "../../core/router.jsx";
import { Icon, errorText, toast } from "../../core/ui.jsx";
import { audienceKey, countryName, openJoin, openRsvp, placeOf, useWhen } from "./shared.jsx";

export function GroupCard({ g }) {
  const { t, lang, fmtNum, langName } = useI18n();
  return (
    <article className="card group-card">
      <div className="row spread">
        <div className="row">
          <span className="badge">{langName(g.lang)}</span>
          {g.audience !== "all" && <span className="badge badge-purple">{t(audienceKey(g.audience))}</span>}
          {g.age_group && g.age_group !== "all" && <span className="badge">{t(`com.age.${g.age_group}`)}</span>}
        </div>
        <span className="faint"><Icon name="users" size={16} /> {t("com.members", { n: fmtNum(g.members) })}</span>
      </div>
      <h3 dir="auto">{g.title}</h3>
      <p className="muted small" dir="auto">{g.description}</p>
      <div className="row spread">
        <span className="faint">{[[g.city, countryName(g.country, lang)].filter(Boolean).join(lang === "ar" ? "، " : ", "), g.leader ? t("com.led_by", { name: g.leader.name }) : ""].filter(Boolean).join(" · ")}</span>
        {g.membership
          ? <a className="btn btn-primary btn-sm" href={`#/groups/${g.id}`}><Icon name="chat" />{t("com.open")}</a>
          : <button type="button" className="btn btn-accent btn-sm" onClick={() => openJoin(g, t, () => navigate(`/groups/${g.id}`))}><Icon name="plus" />{t("com.join")}</button>}
      </div>
    </article>
  );
}

/** What the seeker can do with a meetup now: book it, or, once booked, join online, save it or cancel. */
function MeetupActions({ m, w, reload, account }) {
  const { t } = useI18n();
  const [asking, setAsking] = useState(false);     // the "cancel your booking?" step
  const open = m.registration === "open";
  const online = m.format === "online";
  if (m.status === "cancelled" || w.ended) return null;
  if (!m.my_rsvp) {
    if (w.live) return null;                        // booking closes when it starts
    const full = !open && m.spots_left <= 0;
    return (
      <button type="button" className={`btn btn-sm ${open ? "btn-accent" : "btn-primary"}`} disabled={full}
        onClick={() => openRsvp(m, t, reload, account)}>
        <Icon name={full ? "x" : open ? "plus" : "edit"} />{full ? t("com.full") : t(open ? "com.join_event" : "com.register")}
      </button>
    );
  }
  const cancel = async () => {
    try { await api.post(`/api/meetups/${m.id}/cancel-rsvp`, {}); setAsking(false); reload(); } catch (err) { toast(errorText(err, t), "error"); }
  };
  const code = !online && !open ? m.my_rsvp.code : "";
  return (
    <div className="row meetup-booked">
      <span className="badge badge-mint"><Icon name="check" size={14} />{code ? `${t("com.code")}: ${code}` : t("com.youre_in")}</span>
      {online && m.online_url && (
        <a className={`btn btn-sm ${w.live || w.soon ? "btn-accent" : ""}`} href={m.online_url} target="_blank" rel="noopener noreferrer">
          <Icon name="external" />{t(w.live || w.soon ? "com.join_now" : "com.open_link")}
        </a>
      )}
      {!w.live && <a className="btn btn-sm" href={apiUrl(`/api/meetups/${m.id}/ics`)} download><Icon name="calendar" />{t("com.add_cal")}</a>}
      {!w.live && (asking ? (
        <span className="row cancel-ask">
          <span className="small">{t(open ? "com.leave_q" : "com.cancel_q")}</span>
          <button type="button" className="btn btn-sm btn-danger" onClick={cancel}>{t(open ? "com.leave_yes" : "com.cancel_yes")}</button>
          <button type="button" className="btn btn-ghost btn-sm" autoFocus onClick={() => setAsking(false)}>{t("com.cancel_keep")}</button>
        </span>
      ) : (
        <button type="button" className="btn btn-ghost btn-sm" onClick={() => setAsking(true)}>{t(open ? "com.leave_event" : "com.cancel_rsvp")}</button>
      ))}
    </div>
  );
}

export function MeetupCard({ m, reload, account }) {
  const { t, lang, fmtNum, langName } = useI18n();
  const w = useWhen(m);
  const online = m.format === "online";
  const open = m.registration === "open";
  const cancelled = m.status === "cancelled";
  const full = !open && m.spots_left <= 0;
  const few = !open && !full && m.spots_left <= 5;
  const state = cancelled ? <span className="badge badge-warn">{t("com.cancelled_by_host")}</span>
    : w.live ? <span className="badge badge-live"><span className="live-dot" />{t("com.happening_now")}</span>
      : w.ended ? <span className="badge">{t("com.ended")}</span> : null;
  return (
    <article className={`card meetup-card${cancelled || w.ended ? " is-past" : ""}`}>
      <div className="meetup-date">
        <span className="md-day">{w.day}</span>
        <span className="md-month">{w.month}</span>
      </div>
      <div className="meetup-body">
        <div className="row">
          <span className={`badge ${online ? "badge-online" : ""}`}><Icon name={online ? "globe" : "pin"} size={14} />{t(`com.fmt.${online ? "online" : "in_person"}`)}</span>
          <span className="badge">{langName(m.lang)}</span>
          <span className="badge badge-purple">{t(audienceKey(m.audience))}</span>
          {m.age_group !== "all" && <span className="badge">{t(`com.age.${m.age_group}`)}</span>}
          {state}
        </div>
        {m.series && <span className={`series-tag series-${m.series}`}><Icon name={m.series === "ramadan" ? "moon" : "layers"} size={16} />{t(`com.series.${m.series}`)}</span>}
        <h3 dir="auto">{m.title}</h3>
        {m.description && <p className="muted small" dir="auto">{m.description}</p>}
        <ul className="meta-list">
          <li>
            <Icon name="clock" size={16} />{w.date} · {w.time} · {t("com.minutes", { n: fmtNum(m.duration_min) })}
            {w.countdown && !cancelled && <span className="when-rel">{w.countdown}</span>}
          </li>
          <li>{online
            ? <><Icon name="globe" size={16} />{t(!m.online_url ? "com.online_place" : cancelled || w.ended ? "com.fmt.online" : "com.online_booked")}</>
            : <><Icon name="pin" size={16} /><span dir="auto">{placeOf(m, lang)}</span> <span className="badge">{t("com.public_place")}</span></>}</li>
          {m.host && <li><Icon name="users" size={16} />{t("com.host", { name: m.host.name })}</li>}
        </ul>
        <div className="row spread meetup-actions">
          {cancelled || w.ended ? <span /> : (
            <span className={few ? "spots-few" : "faint"}>
              {open ? t("com.going", { n: fmtNum(m.going) }) : full ? t("com.full") : t(few ? "com.spots_few" : "com.spots", { n: fmtNum(m.spots_left) })}
            </span>
          )}
          <MeetupActions m={m} w={w} reload={reload} account={account} />
        </div>
      </div>
    </article>
  );
}
