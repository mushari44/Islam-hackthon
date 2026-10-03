// Community page: da'i-led groups and in-person meetups. Owner: Mushari (community).
import "./strings.js";
import "./community.css";
import { useEffect, useState } from "react";
import { api } from "../../core/api.js";
import { useI18n } from "../../core/i18n.jsx";
import { navigate } from "../../core/router.jsx";
import { Icon, errorText, toast } from "../../core/ui.jsx";
import { useAccount } from "../account/public.js";
import { AGE_GROUPS, GROUP_AGE_GROUPS, SERIES, audienceKey, countryName, openJoin, openRsvp } from "./shared.jsx";

// A signed-in seeker's own answers preselect the filters. Age bands that span two age groups preselect none.
const AUDIENCE_FROM_GENDER = { f: "women", m: "men" };
const AGE_FROM_BAND = { "18_24": "youth", "35_44": "adults", "45_54": "adults" };

function GroupCard({ g }) {
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
      <h3>{g.title}</h3>
      <p className="muted small">{g.description}</p>
      <div className="row spread">
        <span className="faint">{[[g.city, countryName(g.country, lang)].filter(Boolean).join(lang === "ar" ? "، " : ", "), g.leader ? t("com.led_by", { name: g.leader.name }) : ""].filter(Boolean).join(" · ")}</span>
        {g.membership
          ? <a className="btn btn-primary btn-sm" href={`#/groups/${g.id}`}><Icon name="chat" />{t("com.open")}</a>
          : <button type="button" className="btn btn-accent btn-sm" onClick={() => openJoin(g, t, () => navigate(`/groups/${g.id}`))}><Icon name="plus" />{t("com.join")}</button>}
      </div>
    </article>
  );
}

function MeetupCard({ m, reload, account }) {
  const { t, lang, fmtNum, fmtDate, fmtTime, langName } = useI18n();
  const open = m.registration === "open";
  const full = !open && m.spots_left <= 0;
  // Open events are joined with one tap; ones for a specific audience still ask to confirm it.
  const join = async () => {
    if (m.audience === "women" || m.audience === "men" || m.age_group === "kids") { openRsvp(m, t, reload, account); return; }
    try {
      await api.post(`/api/meetups/${m.id}/rsvp`, { nickname: account ? account.username : t("com.guest") });
      toast(t("com.joined_toast"), "success");
      reload();
    } catch (err) { toast(errorText(err, t), "error"); }
  };
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
          {m.age_group !== "all" && <span className="badge">{t(`com.age.${m.age_group}`)}</span>}
        </div>
        {m.series && <span className={`series-tag series-${m.series}`}><Icon name={m.series === "ramadan" ? "moon" : "layers"} size={16} />{t(`com.series.${m.series}`)}</span>}
        <h3>{m.title}</h3>
        <p className="muted small">{m.description}</p>
        <ul className="meta-list">
          <li><Icon name="clock" size={16} />{fmtDate(m.starts_at)} · {fmtTime(m.starts_at)} · {t("com.minutes", { n: fmtNum(m.duration_min) })}</li>
          <li><Icon name="pin" size={16} />{[m.venue, m.city, countryName(m.country, lang)].filter(Boolean).join(lang === "ar" ? "، " : ", ")} <span className="badge">{t("com.public_place")}</span></li>
          {m.host && <li><Icon name="users" size={16} />{t("com.host", { name: m.host.name })}</li>}
        </ul>
        <div className="row spread">
          <span className="faint">{open ? t("com.going", { n: fmtNum(m.going) }) : full ? t("com.full") : t("com.spots", { n: fmtNum(m.spots_left) })}</span>
          {m.my_rsvp ? (
            <div className="row">
              <span className="badge badge-mint"><Icon name="check" size={14} />{open ? t("com.joined_event") : `${t("com.code")}: ${m.my_rsvp.code}`}</span>
              <a className="btn btn-sm" href={`/api/meetups/${m.id}/ics`} download><Icon name="calendar" />{t("com.add_cal")}</a>
              <button type="button" className="btn btn-ghost btn-sm" onClick={async () => { try { await api.post(`/api/meetups/${m.id}/cancel-rsvp`, {}); reload(); } catch (err) { toast(errorText(err, t), "error"); } }}>{t(open ? "com.leave_event" : "com.cancel_rsvp")}</button>
            </div>
          ) : open ? (
            <button type="button" className="btn btn-accent btn-sm" onClick={join}><Icon name="plus" />{t("com.join_event")}</button>
          ) : (
            <button type="button" className="btn btn-primary btn-sm" disabled={full} onClick={() => openRsvp(m, t, reload, account)}>
              <Icon name="edit" />{full ? t("com.full") : t("com.register")}
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
  const [series, setSeries] = useState(query.series || "");
  const { account } = useAccount();
  const [country, setCountry] = useState(account?.country || "");
  const [city, setCity] = useState(account?.city || "");
  const [audience, setAudience] = useState(AUDIENCE_FROM_GENDER[account?.gender] || "");
  const [age, setAge] = useState(AGE_FROM_BAND[account?.age_band] || "");
  // A signed-in seeker first sees what suits their city, sex and age; they can still pick "all".
  const [placed, setPlaced] = useState(Boolean(account));
  useEffect(() => {
    if (account && !placed) {
      setCountry(account.country || ""); setCity(account.city || "");
      setAudience(AUDIENCE_FROM_GENDER[account.gender] || ""); setAge(AGE_FROM_BAND[account.age_band] || "");
      setPlaced(true);
    }
  }, [account, placed]);
  const ages = tab === "groups" ? GROUP_AGE_GROUPS : AGE_GROUPS;
  const ageValue = age && ages.includes(age) ? age : "";   // there are no children's groups
  const [places, setPlaces] = useState([]);
  useEffect(() => { api.get("/api/community/places").then(setPlaces).catch(() => {}); }, []);
  const cities = (places.find((p) => p.country === country) || {}).cities || [];
  const [items, setItems] = useState(null);
  const [error, setError] = useState(null);
  const [version, setVersion] = useState(0);
  const reload = () => setVersion((v) => v + 1);

  useEffect(() => {
    let alive = true;
    setItems(null);
    setError(null);
    const params = new URLSearchParams({ ui: lang });
    if (langFilter) params.set("lang", langFilter);
    if (country) params.set("country", country);
    if (city) params.set("city", city);
    if (audience) params.set("audience", audience);
    if (ageValue) params.set("age", ageValue);
    if (tab === "meetups" && series) params.set("series", series);
    const q = `?${params}`;
    api.get(`/api/${tab === "groups" ? "groups" : "meetups"}${q}`)
      .then((data) => alive && setItems({ tab, data }))
      .catch((err) => alive && setError(err));
    return () => { alive = false; };
  }, [tab, langFilter, country, city, audience, ageValue, series, lang, version]);

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
      <div className="place-filters">
        <Icon name="pin" size={18} />
        <label className="sr-only" htmlFor="f-country">{t("com.country")}</label>
        <select id="f-country" className="select" value={country} onChange={(e) => { setCountry(e.target.value); setCity(""); }}>
          <option value="">{t("com.all_countries")}</option>
          {places.map((p) => <option key={p.country} value={p.country}>{countryName(p.country, lang)}</option>)}
        </select>
        {country && cities.length > 0 && (
          <>
            <label className="sr-only" htmlFor="f-city">{t("com.city")}</label>
            <select id="f-city" className="select" value={city} onChange={(e) => setCity(e.target.value)}>
              <option value="">{t("com.all_cities")}</option>
              {cities.map((c) => <option key={c} value={c}>{c}</option>)}
            </select>
          </>
        )}
      </div>
      <div className="com-filters">
        <div className="row" role="group" aria-label={t("com.open_to")}>
          <span className="faint">{t("com.open_to")}</span>
          {["", "women", "men"].map((a) => (
            <button key={a || "all"} type="button" className="chip" aria-pressed={audience === a} onClick={() => setAudience(a)}>
              {t(`com.for.${a || "all"}`)}
            </button>
          ))}
        </div>
        <label className="row age-filter">
          <span className="faint">{t("com.age")}</span>
          <select className="select" value={ageValue} onChange={(e) => setAge(e.target.value)}>
            {ages.map((a) => <option key={a} value={a === "all" ? "" : a}>{t(`com.age.${a}`)}</option>)}
          </select>
        </label>
        {tab === "meetups" && SERIES.map((sr) => (
          <button key={sr} type="button" className="chip series-chip" aria-pressed={series === sr} onClick={() => setSeries(series === sr ? "" : sr)}>
            <Icon name={sr === "ramadan" ? "moon" : "layers"} size={16} />{t(`com.series.${sr}`)}
          </button>
        ))}
      </div>
      {tab === "meetups" && series && <p className="series-lead"><Icon name={series === "ramadan" ? "moon" : "layers"} size={18} />{t(`com.series_lead.${series}`)}</p>}
      {error && <p className="empty">{errorText(error, t)}</p>}
      {!error && (!items || items.tab !== tab) && <div className="skeleton" style={{ height: 120 }} />}
      {items && items.tab === tab && tab === "groups" && (items.data.length
        ? <div className="grid grid-2">{items.data.map((g) => <GroupCard key={g.id} g={g} />)}</div>
        : <p className="empty">{t("com.empty_groups")}</p>)}
      {items && items.tab === tab && tab === "meetups" && (items.data.length
        ? <div className="stack">{items.data.map((m) => <MeetupCard key={m.id} m={m} reload={reload} account={account} />)}</div>
        : <p className="empty">{t("com.empty_meetups")}</p>)}
    </>
  );
}
