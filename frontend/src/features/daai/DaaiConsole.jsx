// Da'i console: login, availability and the tabs (calls, call log, groups, meetups, profile, and da'i accounts for the reviewer). Owner: Eman.
import "./strings.js";
import { useEffect, useState } from "react";
import { api, daaiAuth } from "../../core/api.js";
import { useI18n } from "../../core/i18n.jsx";
import { Icon, errorText, toast, usePolling } from "../../core/ui.jsx";
import { callsTab } from "./CallsTab.jsx";
import { groupsTab, meetupsTab } from "./CommunityTabs.jsx";
import { profileTab, titledName } from "./ProfileTab.jsx";
import { historyTab } from "./HistoryTab.jsx";
import { adminTab } from "./AdminTab.jsx";

const TABS = [callsTab, historyTab, groupsTab, meetupsTab, profileTab, adminTab];
const tabsFor = (me) => TABS.filter((x) => !x.adminOnly || me?.role === "admin");


function Login({ onLogin }) {
  const { t } = useI18n();
  const [user, setUser] = useState("");
  const [pass, setPass] = useState("");
  const submit = async (e) => {
    e.preventDefault();
    try {
      const res = await api.post("/api/daai/login", { username: user, password: pass }, { as: "none" });
      daaiAuth.set(res.token);
      onLogin(res.me);
    } catch (err) {
      const key = { 401: "dai.bad", 403: "dai.disabled", 429: "dai.too_many" }[err.status];
      toast(key ? t(key) : errorText(err, t), "error");
    }
  };
  return (
    <>
      <div className="page-head"><h1>{t("dai.title")}</h1><p>{t("dai.lead")}</p></div>
      <form className="card stack login-card" onSubmit={submit}>
        <div className="field"><label htmlFor="du">{t("dai.user")}</label><input id="du" className="input" autoComplete="username" required value={user} onChange={(e) => setUser(e.target.value)} /></div>
        <div className="field"><label htmlFor="dp">{t("dai.pass")}</label><input id="dp" className="input" type="password" autoComplete="current-password" required value={pass} onChange={(e) => setPass(e.target.value)} /></div>
        <div className="row"><button type="submit" className="btn btn-primary"><Icon name="lock" />{t("dai.login")}</button></div>
        <p className="faint">{t("dai.demo")}</p>
      </form>
    </>
  );
}

export default function DaaiConsole({ query }) {
  const { t, lang, langName } = useI18n();
  const [me, setMe] = useState(null);
  const [checked, setChecked] = useState(false);
  const [tab, setTab] = useState(TABS.find((x) => x.key === query.tab) || TABS[0]);

  useEffect(() => {
    if (!daaiAuth.token) { setChecked(true); return; }
    api.dGet("/api/daai/me").then(setMe).catch(() => daaiAuth.clear()).finally(() => setChecked(true));
  }, []);
  // keep "last seen" fresh so seekers see this da'i as online
  usePolling(() => api.dGet("/api/daai/me"), 30000, [], Boolean(me));

  if (!checked) return null;
  if (!me) return <Login onLogin={setMe} />;

  const setAvailable = async (e) => {
    try { setMe(await api.dPost("/api/daai/availability", { available: e.target.checked })); } catch (err) { toast(errorText(err, t), "error"); }
  };
  const shown = tabsFor(me).includes(tab) ? tab : TABS[0];
  const Panel = shown.component;
  return (
    <>
      <div className="page-head row spread">
        <div>
          <h1>{t("dai.title")}</h1>
          <p>{titledName(me, lang, t)} · {t("dai.langs", { l: (me.languages || []).map(langName).join(lang === "ar" ? "، " : ", ") })}</p>
        </div>
        <div className="row">
          <label className="row"><span className="switch"><input type="checkbox" checked={me.available} onChange={setAvailable} /><span /></span><span>{t("dai.available")}</span></label>
          <button type="button" className="btn btn-danger-soft btn-sm" onClick={() => { daaiAuth.clear(); setMe(null); }}><Icon name="logout" />{t("dai.logout")}</button>
        </div>
      </div>
      <div className="tabs" role="tablist">
        {tabsFor(me).map((x) => <button key={x.key} type="button" role="tab" aria-selected={x === shown} onClick={() => setTab(x)}>{t(x.labelKey)}</button>)}
      </div>
      <div className="section daai-panel"><Panel me={me} onMe={setMe} key={shown.key} /></div>
    </>
  );
}
