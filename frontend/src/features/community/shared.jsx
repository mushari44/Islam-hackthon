// Pieces shared inside the community feature: rules, join and RSVP forms. Owner: Mushari.
import "./strings.js";
import "./community.css";
import { useState } from "react";
import { api } from "../../core/api.js";
import { useI18n } from "../../core/i18n.jsx";
import { Icon, errorText, openSheet, toast } from "../../core/ui.jsx";
import { useAccount } from "../account/public.js";

export const audienceKey = (a) => ({ women: "com.women", men: "com.men", families: "com.families" }[a] || "com.everyone");

// Meetup types: booking needed or walk-in, an age group, and an optional series.
export const REGISTRATION = ["required", "open"];
export const AGE_GROUPS = ["all", "kids", "youth", "adults", "seniors"];
export const SERIES = ["ramadan", "qawl_amal"];

// Countries a da'i can pick when creating a group or meetup (ISO codes); names come from the browser.
export const COUNTRIES = ["SA", "AE", "KW", "QA", "BH", "OM", "EG", "JO", "MA", "DZ", "TN", "IQ",
  "GB", "US", "CA", "AU", "IE", "DE", "FR", "NL", "SE", "TR", "MY", "ID", "SG", "PH", "NG", "KE", "ZA"];
const regionNames = {};
export function countryName(code, lang) {
  if (!code) return "";
  try {
    regionNames[lang] = regionNames[lang] || new Intl.DisplayNames([lang], { type: "region" });
    return regionNames[lang].of(code) || code;
  } catch { return code; }
}

export function Rules() {
  const { t } = useI18n();
  return <ul className="rules">{["com.rule1", "com.rule2", "com.rule3", "com.rule4"].map((k) => <li key={k}>{t(k)}</li>)}</ul>;
}

const needsAudience = (audience) => audience === "women" || audience === "men";

function JoinForm({ group, close, onJoined }) {
  const { t, lang } = useI18n();
  const { account } = useAccount();
  const [nick, setNick] = useState(account ? account.username : "");
  const [accept, setAccept] = useState(false);
  const [confirm, setConfirm] = useState(false);
  const [busy, setBusy] = useState(false);
  const needsConfirm = needsAudience(group.audience);
  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      await api.post(`/api/groups/${group.id}/join?ui=${lang}`, { nickname: nick, accept_rules: accept, confirm_audience: confirm });
      toast(t("com.joined"));
      close();
      onJoined?.();
    } catch (err) {
      toast(errorText(err, t), "error");
      setBusy(false);
    }
  };
  return (
    <form className="stack" onSubmit={submit}>
      <div className="field">
        <label htmlFor="nick">{t("com.nickname")}</label>
        <input id="nick" className="input" maxLength={24} autoComplete="off" value={nick} onChange={(e) => setNick(e.target.value)} />
        <span className="hint">{t("com.nick_hint")}</span>
      </div>
      <div><h3>{t("com.rules")}</h3><Rules /></div>
      {needsConfirm && (
        <label className="check"><input type="checkbox" checked={confirm} onChange={(e) => setConfirm(e.target.checked)} />
          <span>{t("com.confirm_group_aud", { aud: t(audienceKey(group.audience)) })}</span></label>
      )}
      <label className="check"><input type="checkbox" checked={accept} onChange={(e) => setAccept(e.target.checked)} /><span>{t("com.accept")}</span></label>
      <div className="row"><button type="submit" className="btn btn-primary" disabled={busy || !accept || (needsConfirm && !confirm) || nick.trim().length < 2}>{t("com.join")}</button></div>
    </form>
  );
}

export function openJoin(group, t, onJoined) {
  openSheet({ title: t("com.join_title", { title: group.title }), render: (close) => <JoinForm group={group} close={close} onJoined={onJoined} /> });
}

function RsvpForm({ meetup, onDone, account }) {
  const { t, lang } = useI18n();
  const [nick, setNick] = useState(account ? account.username : "");
  const [confirm, setConfirm] = useState(false);
  const [code, setCode] = useState(null);
  const [busy, setBusy] = useState(false);
  const forKids = meetup.age_group === "kids";
  const needsConfirm = forKids || needsAudience(meetup.audience);
  const open = meetup.registration === "open";
  if (code && open) {
    return (
      <div className="stack center">
        <p className="booking-code"><Icon name="check" size={28} /></p>
        <p>{t("com.joined_toast")}</p>
        <a className="btn btn-primary" href={`/api/meetups/${meetup.id}/ics`} download><Icon name="calendar" />{t("com.add_cal")}</a>
      </div>
    );
  }
  if (code) {
    return (
      <div className="stack center">
        <p className="muted">{t("com.code")}</p>
        <p className="booking-code">{code}</p>
        <a className="btn btn-primary" href={`/api/meetups/${meetup.id}/ics`} download><Icon name="calendar" />{t("com.add_cal")}</a>
      </div>
    );
  }
  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      const res = await api.post(`/api/meetups/${meetup.id}/rsvp?ui=${lang}`, { nickname: nick, confirm_audience: confirm });
      setCode(res.my_rsvp.code);
      onDone?.();
    } catch (err) {
      toast(errorText(err, t), "error");
      setBusy(false);
    }
  };
  return (
    <form className="stack" onSubmit={submit}>
      {!open && <p className="small muted">{t("com.rsvp_note")}</p>}
      <div className="field">
        <label htmlFor="rsvp-nick">{t("com.nickname")}</label>
        <input id="rsvp-nick" className="input" maxLength={24} autoComplete="off" value={nick} onChange={(e) => setNick(e.target.value)} />
      </div>
      {needsConfirm && (
        <label className="check"><input type="checkbox" checked={confirm} onChange={(e) => setConfirm(e.target.checked)} />
          <span>{forKids ? t("com.confirm_guardian") : t("com.confirm_aud", { aud: t(audienceKey(meetup.audience)) })}</span></label>
      )}
      <div className="row"><button type="submit" className="btn btn-primary" disabled={busy || nick.trim().length < 2 || (needsConfirm && !confirm)}>{t(open ? "com.join_event" : "com.register")}</button></div>
    </form>
  );
}

export function openRsvp(meetup, t, onDone, account = null) {
  const title = t(meetup.registration === "open" ? "com.join_title_event" : "com.rsvp_title", { title: meetup.title });
  openSheet({ title, render: () => <RsvpForm meetup={meetup} onDone={onDone} account={account} /> });
}
