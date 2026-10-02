// Community page: da'i-led groups and in-person meetups. Owner: Mushari (community).
import "./strings.js";
import "./community.css";
import { useEffect, useState } from "react";
import { api } from "../../core/api.js";
import { useI18n } from "../../core/i18n.jsx";
import { navigate } from "../../core/router.jsx";
import { Icon, errorText, toast } from "../../core/ui.jsx";
import { audienceKey, openJoin, openRsvp } from "./shared.jsx";

function GroupCard({ g }) {
  const { t, fmtNum, langName } = useI18n();
  return (
    <article className="card group-card">
      <div className="row spread">
        <div className="row">
          <span className="badge">{langName(g.lang)}</span>
          {g.audience !== "all" && <span className="badge badge-purple">{t(audienceKey(g.audience))}</span>}
          {g.is_demo && <span className="badge badge-warn">{t("common.demo")}</span>}
        </div>
        <span className="faint"><Icon name="users" size={16} /> {t("com.members", { n: fmtNum(g.members) })}</span>
      </div>
      <h3>{g.title}</h3>
      <p className="muted small">{g.description}</p>
      <div className="row spread">
        <span className="faint">{[g.city, g.leader ? t("com.led_by", { name: g.leader.name }) : ""].filter(Boolean).join(" · ")}</span>
        {g.membership
          ? <a className="btn btn-primary btn-sm" href={`#/groups/${g.id}`}><Icon name="chat" />{t("com.open")}</a>
          : <button type="button" className="btn btn-accent btn-sm" onClick={() => openJoin(g, t, () => navigate(`/groups/${g.id}`))}><Icon name="plus" />{t("com.join")}</button>}
      </div>
    </article>
  );
}

function MeetupCard({ m, reload }) {
  const { t, lang, fmtNum, fmtDate, fmtTime, langName } = useI18n();
  const full = m.spots_left <= 0;
  return (
    <article className="card meetup-card">
      <div className="meetup-date">
        <span className="md-day">{fmtDate(m.starts_at, { day: "numeric" })}</span>
        <span className="md-month">{fmtDate(m.starts_at, { month: "short" })}</span>
      </div>
      <div className="meetup-body">
        <div className="row">
          <span className="badge">{langName(m.lang)}</span>
          <span className="badge badge-purple">{t(audienceKey(m.audience))}</span>
          {m.is_demo && <span className="badge badge-warn">{t("common.demo")}</span>}
        </div>
        <h3>{m.title}</h3>
        <p className="muted small">{m.description}</p>
        <ul className="meta-list">
          <li><Icon name="clock" size={16} />{fmtDate(m.starts_at)} · {fmtTime(m.starts_at)} · {t("com.minutes", { n: fmtNum(m.duration_min) })}</li>
          <li><Icon name="pin" size={16} />{[m.venue, m.city].filter(Boolean).join(lang === "ar" ? "، " : ", ")} <span className="badge">{t("com.public_place")}</span></li>
          {m.host && <li><Icon name="users" size={16} />{t("com.host", { name: m.host.name })}</li>}
        </ul>
        <div className="row spread">
          <span className="faint">{full ? t("com.full") : t("com.spots", { n: fmtNum(m.spots_left) })}</span>
          {m.my_rsvp ? (
            <div className="row">
              <span className="badge badge-mint">{t("com.code")}: {m.my_rsvp.code}</span>
              <a className="btn btn-sm" href={`/api/meetups/${m.id}/ics`} download><Icon name="calendar" />{t("com.add_cal")}</a>
              <button type="button" className="btn btn-ghost btn-sm" onClick={async () => { try { await api.post(`/api/meetups/${m.id}/cancel-rsvp`, {}); reload(); } catch (err) { toast(errorText(err, t), "error"); } }}>{t("com.cancel_rsvp")}</button>
            </div>
          ) : (
            <button type="button" className="btn btn-accent btn-sm" disabled={full} onClick={() => openRsvp(m, t, reload)}>
              <Icon name="calendar" />{full ? t("com.full") : t("com.rsvp")}
            </button>
          )}
        </div>
      </div>
    </article>
  );
}

export default function CommunityPage({ query }) {
  const { t, lang, langName } = useI18n();
  const [tab, setTab] = useState(query.tab === "meetups" ? "meetups" : "groups");
  const [langFilter, setLangFilter] = useState("");
  const [items, setItems] = useState(null);
  const [error, setError] = useState(null);
  const [version, setVersion] = useState(0);
  const reload = () => setVersion((v) => v + 1);

  useEffect(() => {
    let alive = true;
    setItems(null);
    setError(null);
    const q = `?ui=${lang}${langFilter ? `&lang=${langFilter}` : ""}`;
    api.get(`/api/${tab === "groups" ? "groups" : "meetups"}${q}`)
      .then((data) => alive && setItems({ tab, data }))
      .catch((err) => alive && setError(err));
    return () => { alive = false; };
  }, [tab, langFilter, lang, version]);

  return (
    <>
      <div className="page-head"><h1>{t("com.title")}</h1><p>{t("com.lead")}</p></div>
      <div className="row spread com-bar">
        <div className="tabs" role="tablist">
          {[["groups", "com.groups"], ["meetups", "com.meetups"]].map(([k, label]) => (
            <button key={k} type="button" role="tab" aria-selected={tab === k} onClick={() => setTab(k)}>{t(label)}</button>
          ))}
        </div>
        <div className="row">
          {["", "ar", "en"].map((l) => (
            <button key={l || "all"} type="button" className="chip" aria-pressed={langFilter === l} onClick={() => setLangFilter(l)}>
              {l ? langName(l) : t("com.all_langs")}
            </button>
          ))}
        </div>
      </div>
      {error && <p className="empty">{errorText(error, t)}</p>}
      {!error && (!items || items.tab !== tab) && <div className="skeleton" style={{ height: 120 }} />}
      {items && items.tab === tab && tab === "groups" && (items.data.length
        ? <div className="grid grid-2">{items.data.map((g) => <GroupCard key={g.id} g={g} />)}</div>
        : <p className="empty">{t("com.empty_groups")}</p>)}
      {items && items.tab === tab && tab === "meetups" && (items.data.length
        ? <div className="stack">{items.data.map((m) => <MeetupCard key={m.id} m={m} reload={reload} />)}</div>
        : <p className="empty">{t("com.empty_meetups")}</p>)}
    </>
  );
}
