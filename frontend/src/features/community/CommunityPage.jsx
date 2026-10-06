// Community page: da'i-led groups and in-person meetups. Owner: Mushari (community).
import "./strings.js";
import "./community.css";
import { useEffect, useState } from "react";
import { api } from "../../core/api.js";
import { useI18n } from "../../core/i18n.jsx";
import { navigate } from "../../core/router.jsx";
import { Icon, errorText } from "../../core/ui.jsx";
import { useAccount } from "../account/public.js";
import MyActivities from "./MyActivities.jsx";
import { NewMuslimPrompt } from "./NewMuslim.jsx";
import { GroupCard, MeetupCard } from "./cards.jsx";
import { AGE_GROUPS, FORMATS, GROUP_AGE_GROUPS, SERIES, countryName, useNow } from "./shared.jsx";

const TABS = ["groups", "meetups", "mine"];

// A signed-in seeker's own answers preselect the filters. Age bands that span two age groups preselect none.
const AUDIENCE_FROM_GENDER = { f: "women", m: "men" };
const AGE_FROM_BAND = { "18_24": "youth", "35_44": "adults", "45_54": "adults" };

export default function CommunityPage({ query }) {
  const { t, tn, lang, fmtNum, langName } = useI18n();
  // The tab lives in the address (#/community?tab=mine), so links such as "Go to My activities" always work.
  const tab = TABS.includes(query.tab) ? query.tab : "groups";
  const setTab = (k) => navigate(`/community?tab=${k}`);
  const [langFilter, setLangFilter] = useState("");
  const [fmt, setFmt] = useState("");
  const [series, setSeries] = useState(query.series || "");
  const { account } = useAccount();
  const [country, setCountry] = useState(account?.country || "");
  const [city, setCity] = useState(account?.city || "");
  const [audience, setAudience] = useState(AUDIENCE_FROM_GENDER[account?.gender] || "");
  const [age, setAge] = useState(AGE_FROM_BAND[account?.age_band] || "");
  // A signed-in seeker first sees what suits their city, sex and age (again after they change them); they can still
  // pick "all".
  const who = account ? [account.username, account.country, account.city, account.gender, account.age_band].join("|") : "";
  const [placed, setPlaced] = useState(who);
  useEffect(() => {
    if (who && who !== placed) {
      setCountry(account.country || ""); setCity(account.city || "");
      setAudience(AUDIENCE_FROM_GENDER[account.gender] || ""); setAge(AGE_FROM_BAND[account.age_band] || "");
      setPlaced(who);
    }
  }, [who, placed]); // eslint-disable-line react-hooks/exhaustive-deps
  const ages = tab === "groups" ? GROUP_AGE_GROUPS : AGE_GROUPS;
  const ageValue = age && ages.includes(age) ? age : "";   // there are no children's groups
  const [places, setPlaces] = useState([]);
  useEffect(() => { api.get("/api/community/places").then(setPlaces).catch(() => {}); }, []);
  const cities = (places.find((p) => p.country === country) || {}).cities || [];
  const [items, setItems] = useState(null);
  const [error, setError] = useState(null);
  const [version, setVersion] = useState(0);
  const reload = () => setVersion((v) => v + 1);
  // What this seeker takes part in: the "My activities" tab, and the count on it.
  const [mine, setMine] = useState(null);
  useEffect(() => {
    let alive = true;
    api.get(`/api/community/mine?ui=${lang}`).then((d) => alive && setMine(d)).catch((err) => alive && setMine({ error: err }));
    return () => { alive = false; };
  }, [lang, version, account]);
  const now = useNow();
  const upcoming = mine?.meetups ? mine.meetups.filter((m) => m.status === "open" && new Date(m.starts_at).getTime() + m.duration_min * 60000 > now).length : 0;

  // Which list is showing: a new list shows a placeholder while it loads; a refresh after booking keeps the old one.
  const listKey = [tab, langFilter, country, city, audience, ageValue, series, fmt, lang].join("|");
  // Any filter narrowing the list: then the count line offers "Clear filters", as list pages usually do.
  const filtered = Boolean(langFilter || country || city || audience || ageValue || (tab === "meetups" && (series || fmt)));
  const clearFilters = () => { setLangFilter(""); setFmt(""); setSeries(""); setCountry(""); setCity(""); setAudience(""); setAge(""); };
  useEffect(() => {
    if (tab === "mine") return undefined;
    let alive = true;
    setError(null);
    const params = new URLSearchParams({ ui: lang });
    if (langFilter) params.set("lang", langFilter);
    if (country) params.set("country", country);
    if (city) params.set("city", city);
    if (audience) params.set("audience", audience);
    if (ageValue) params.set("age", ageValue);
    if (tab === "meetups" && series) params.set("series", series);
    if (tab === "meetups" && fmt) params.set("format", fmt);
    const q = `?${params}`;
    api.get(`/api/${tab === "groups" ? "groups" : "meetups"}${q}`)
      .then((data) => alive && setItems({ key: listKey, tab, data }))
      .catch((err) => alive && setError(err));
    return () => { alive = false; };
  }, [tab, langFilter, country, city, audience, ageValue, series, fmt, lang, version]);

  return (
    <>
      <div className="page-head"><h1>{t("com.title")}</h1><p>{t("com.lead")}</p></div>
      <NewMuslimPrompt manage />
      <div className="row spread com-bar">
        <div className="tabs" role="tablist">
          {[["groups", "com.groups"], ["meetups", "com.meetups"], ["mine", "com.mine"]].map(([k, label]) => (
            <button key={k} type="button" role="tab" aria-selected={tab === k} onClick={() => setTab(k)}>
              {t(label)}{k === "mine" && upcoming > 0 && <span className="tab-count">{fmtNum(upcoming)}</span>}
            </button>
          ))}
        </div>
      </div>
      {tab === "mine" && <MyActivities data={mine} reload={reload} account={account} browse={setTab} />}
      {tab !== "mine" && (
        <>
          <div className="com-filter-panel" role="group" aria-label={t("com.filters")}>
            <div className="row" role="group" aria-label={t("com.lang")}>
              {["", "ar", "en"].map((l) => (
                <button key={l || "all"} type="button" className="chip" aria-pressed={langFilter === l} onClick={() => setLangFilter(l)}>
                  {l ? langName(l) : t("com.all_langs")}
                </button>
              ))}
            </div>
            {tab === "meetups" && (
              <div className="row format-filter" role="group" aria-label={t("com.format")}>
                {["", ...FORMATS].map((f) => (
                  <button key={f || "all"} type="button" className="chip" aria-pressed={fmt === f} onClick={() => setFmt(f)}>
                    {f && <Icon name={f === "online" ? "globe" : "pin"} size={16} />}{t(`com.fmt.${f || "all"}`)}
                  </button>
                ))}
              </div>
            )}
            {fmt !== "online" || tab !== "meetups" ? (
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
                {tab === "meetups" && country && !fmt && <span className="faint small">{t("com.online_everywhere")}</span>}
              </div>
            ) : null}
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
          </div>
          {tab === "meetups" && series && <p className="series-lead"><Icon name={series === "ramadan" ? "moon" : "layers"} size={18} />{t(`com.series_lead.${series}`)}</p>}
          {error && (
            <div className="empty">
              <p>{errorText(error, t)}</p>
              <button type="button" className="btn btn-sm" onClick={reload}>{t("common.retry")}</button>
            </div>
          )}
          {!error && items?.key !== listKey && <div className="skeleton" style={{ height: 120 }} />}
          {!error && items?.key === listKey && (
            <div className="row spread com-results">
              <span className="faint small" role="status">{tn(tab === "groups" ? "com.n_groups" : "com.n_meetups", items.data.length)}</span>
              {filtered && <button type="button" className="link-btn small" onClick={clearFilters}><Icon name="x" size={14} />{t("com.clear_filters")}</button>}
            </div>
          )}
          {!error && items?.key === listKey && tab === "groups" && (items.data.length
            ? <div className="grid grid-2">{items.data.map((g) => <GroupCard key={g.id} g={g} />)}</div>
            : <p className="empty">{t("com.empty_groups")}</p>)}
          {!error && items?.key === listKey && tab === "meetups" && (items.data.length
            ? <div className="stack">{items.data.map((m) => <MeetupCard key={m.id} m={m} reload={reload} account={account} />)}</div>
            : <p className="empty">{t("com.empty_meetups")}</p>)}
        </>
      )}
    </>
  );
}
