// Da'i console shell: login, availability, and tabs contributed by features. Shared.
// Calls tab: features/calls (Eman). Groups and Meetups tabs: features/community (Mushari).
import { useEffect, useState } from "react";
import { api, daaiAuth } from "../core/api.js";
import { register, useI18n } from "../core/i18n.jsx";
import { Icon, errorText, toast, usePolling } from "../core/ui.jsx";
import { callsTab } from "../features/calls/index.js";
import { communityTabs } from "../features/community/index.js";

const TABS = [callsTab, ...communityTabs];

register({
  ar: {
    "dai.title": "لوحة الداعية", "dai.lead": "للدعاة والمراجعين فقط. استقبل طلبات الاتصال بلغاتك، وقُد مجموعاتك، وانشر لقاءاتك.",
    "dai.user": "اسم المستخدم", "dai.pass": "كلمة المرور", "dai.login": "دخول", "dai.bad": "اسم المستخدم أو كلمة المرور غير صحيحة.",
    "dai.demo": "حسابات تجريبية للتحكيم: khalid و maryam و yusuf و reviewer. كلمة المرور في ملف README.",
    "dai.available": "متاح لاستقبال المكالمات", "dai.logout": "خروج", "dai.langs": "لغاتك: {l}",
  },
  en: {
    "dai.title": "Da'i console", "dai.lead": "For da'is and reviewers only. Take call requests in your languages, lead your groups and publish meetups.",
    "dai.user": "Username", "dai.pass": "Password", "dai.login": "Sign in", "dai.bad": "Wrong username or password.",
    "dai.demo": "Demo accounts for judging: khalid, maryam, yusuf and reviewer. The password is in the README.",
    "dai.available": "Available for calls", "dai.logout": "Sign out", "dai.langs": "Your languages: {l}",
  },
});

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
      toast(err.status === 401 ? t("dai.bad") : errorText(err, t), "error");
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
  const Panel = tab.component;
  return (
    <>
      <div className="page-head row spread">
        <div>
          <h1>{t("dai.title")}</h1>
          <p>{lang === "ar" ? me.name : me.name_en || me.name} · {t("dai.langs", { l: (me.languages || []).map(langName).join(lang === "ar" ? "، " : ", ") })}</p>
        </div>
        <div className="row">
          <label className="row"><span className="switch"><input type="checkbox" checked={me.available} onChange={setAvailable} /><span /></span><span>{t("dai.available")}</span></label>
          <button type="button" className="btn btn-ghost btn-sm" onClick={() => { daaiAuth.clear(); setMe(null); }}><Icon name="logout" />{t("dai.logout")}</button>
        </div>
      </div>
      <div className="tabs" role="tablist">
        {TABS.map((x) => <button key={x.key} type="button" role="tab" aria-selected={x === tab} onClick={() => setTab(x)}>{t(x.labelKey)}</button>)}
      </div>
      <div className="section daai-panel"><Panel me={me} key={tab.key} /></div>
    </>
  );
}
