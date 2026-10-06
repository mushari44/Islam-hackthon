// Da'i console: sign-in (through the shared card), availability and the tabs (calls, my schedule, call log, groups, meetups, profile, and da'i accounts for the reviewer). Owner: Eman.
import "./strings.js";
import "./daai.css";
import { useEffect, useRef, useState } from "react";
import { api, daaiAuth } from "../../core/api.js";
import { setDaaiToken } from "../account/public.js";
import { SignInCard } from "../account/index.js";   // not in public.js: community imports that, and the card imports community
import { useI18n } from "../../core/i18n.jsx";
import { navigate } from "../../core/router.jsx";
import { Spinner, errorText, toast, usePolling } from "../../core/ui.jsx";
import { AskFirst, LoadError } from "./bits.jsx";
import CallsTab, { callsTab } from "./CallsTab.jsx";
import { groupsTab, meetupsTab } from "./CommunityTabs.jsx";
import { profileTab, titledName } from "./ProfileTab.jsx";
import { historyTab } from "./HistoryTab.jsx";
import { scheduleTab } from "./ScheduleTab.jsx";
import { adminTab } from "./AdminTab.jsx";

const TABS = [callsTab, scheduleTab, historyTab, groupsTab, meetupsTab, profileTab, adminTab];
const tabsFor = (me) => TABS.filter((x) => (!x.adminOnly || me?.role === "admin") && (!x.daaiOnly || me?.role === "daai"));
// Only these mean the token is no longer good; anything else (offline, a server error) is worth a retry.
const sessionGone = (err) => err && (err.status === 401 || err.status === 403);

export default function DaaiConsole({ query }) {
  const { t, lang, langName, tn, fmtNum } = useI18n();
  const [me, setMe] = useState(null);
  const [check, setCheck] = useState(daaiAuth.token ? { state: "checking" } : { state: "done" });
  const [callId, setCallId] = useState(null);      // the call in progress, if any (reported by the calls tab)
  const [waiting, setWaiting] = useState(0);        // requests waiting, for the badge on the calls tab
  const [switching, setSwitching] = useState(false);
  const tabsRef = useRef(null);

  const endSession = () => { setDaaiToken(null); setMe(null); toast(t("dai.session_ended"), "error"); };
  const checkSession = () => {
    if (!daaiAuth.token) { setCheck({ state: "done" }); return; }
    setCheck({ state: "checking" });
    api.dGet("/api/daai/me").then((d) => { setMe(d); setCheck({ state: "done" }); }).catch((err) => {
      if (sessionGone(err)) { endSession(); setCheck({ state: "done" }); } else setCheck({ state: "error", err });
    });
  };
  useEffect(() => { checkSession(); }, []); // eslint-disable-line react-hooks/exhaustive-deps
  // keeps "last seen" fresh so seekers see this da'i as online, and notices a session that ended elsewhere
  usePolling(async () => {
    // The answer isn't kept: it could be older than a switch or profile save made meanwhile.
    try { await api.dGet("/api/daai/me"); } catch (err) { if (sessionGone(err)) endSession(); }
  }, 30000, [], Boolean(me));

  const list = me ? tabsFor(me) : [];
  const shown = list.find((x) => x.key === query.tab) || list[0];
  // On a phone the tab bar scrolls sideways: keep the current tab in sight.
  useEffect(() => {
    tabsRef.current?.querySelector('[aria-selected="true"]')?.scrollIntoView({ block: "nearest", inline: "nearest" });
  }, [shown?.key]);

  if (check.state === "checking") return <div className="section"><Spinner /></div>;
  if (check.state === "error") return <div className="section"><LoadError err={check.err} onRetry={checkSession} /></div>;
  // Signed out: the site's one sign-in card, with "da'i" already picked (seekers can switch to "user" there).
  if (!me) return <div className="auth-page"><SignInCard role="daai" onDaaiSignIn={setMe} /></div>;

  const setAvailable = async (e) => {
    setSwitching(true);
    try { setMe(await api.dPost("/api/daai/availability", { available: e.target.checked })); } catch (err) { toast(errorText(err, t), "error"); }
    setSwitching(false);
  };
  const signOut = async () => {
    // A signed-out da'i must not stay listed as available, and a call in progress ends for the seeker too.
    await api.dPost("/api/daai/availability", { available: false }).catch(() => {});
    if (callId) await api.dPost(`/api/daai/calls/${callId}/end`, {}).catch(() => {});
    setDaaiToken(null);
    setMe(null);
    setCallId(null);
  };
  const Panel = shown.component;
  return (
    <>
      <div className="page-head row spread">
        <div>
          <h1>{t("dai.title")}</h1>
          <p>{titledName(me, lang, t)} · {t("dai.langs", { l: (me.languages || []).map(langName).join(lang === "ar" ? "، " : ", ") })}</p>
        </div>
        <div className="row">
          <label className={`row${switching ? " daai-busy" : ""}`}>
            <span className="switch"><input type="checkbox" checked={me.available} disabled={switching} onChange={setAvailable} /><span /></span>
            <span>{t("dai.available")}</span>
          </label>
          <AskFirst label={t("dai.logout")} icon="logout" ask={Boolean(callId)} question={t("dai.logout_q")} no={t("dai.logout_keep")} onYes={signOut} />
        </div>
      </div>
      <div className="tabs" role="tablist" ref={tabsRef}>
        {list.map((x) => (
          <button key={x.key} id={`daai-tab-${x.key}`} type="button" role="tab" aria-selected={x === shown} aria-controls={`daai-panel-${x.key}`}
            onClick={() => navigate(`/daai?tab=${x.key}`)}>
            {t(x.labelKey)}
            {x === callsTab && waiting > 0 && <>
              <span className="daai-tab-count" aria-hidden="true">{fmtNum(waiting)}</span>
              <span className="sr-only">{tn("dc.waiting_n", waiting)}</span>
            </>}
          </button>
        ))}
      </div>
      {/* The calls tab stays mounted while another tab is shown, so a call, its after-call form and the
          waiting-request count survive a look at the call log or the groups. */}
      <div className="section daai-panel" id="daai-panel-calls" role="tabpanel" aria-labelledby="daai-tab-calls" hidden={shown !== callsTab}>
        <CallsTab me={me} onCall={setCallId} onWaiting={setWaiting} />
      </div>
      {shown !== callsTab && (
        <div className="section daai-panel" id={`daai-panel-${shown.key}`} role="tabpanel" aria-labelledby={`daai-tab-${shown.key}`}>
          <Panel me={me} onMe={setMe} key={shown.key} />
        </div>
      )}
    </>
  );
}
