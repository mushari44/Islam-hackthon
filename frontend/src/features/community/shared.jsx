// Pieces shared inside the community feature: rules, join and RSVP forms. Owner: Mushari.
import "./strings.js";
import "./community.css";
import { useState } from "react";
import { api } from "../../core/api.js";
import { useI18n } from "../../core/i18n.jsx";
import { navigate } from "../../core/router.jsx";
import { Icon, errorText, openSheet, toast } from "../../core/ui.jsx";
import { useAccount } from "../account/public.js";

export const audienceKey = (a) => ({ women: "com.women", men: "com.men", families: "com.families" }[a] || "com.everyone");

// Meetup types: booking needed or walk-in, an age group, and an optional series.
export const REGISTRATION = ["required", "open"];
export const AGE_GROUPS = ["all", "kids", "youth", "adults", "seniors"];
export const GROUP_AGE_GROUPS = ["all", "youth", "adults", "seniors"];   // no children's groups online
export const SERIES = ["ramadan", "qawl_amal"];
// Where it happens: a public venue, or an online meeting whose link only people who booked receive.
export const FORMATS = ["in_person", "online"];

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

const VIEWER_TZ = (() => { try { return Intl.DateTimeFormat().resolvedOptions().timeZone; } catch { return ""; } })();

/** Intl options showing an in-person meetup in its venue's time zone; an online one shows in the viewer's own. */
function zoneOf(m) {
  if (m.format === "online" || !m.tz) return {};
  try { new Intl.DateTimeFormat("en", { timeZone: m.tz }); return { timeZone: m.tz }; } catch { return {}; }
}

/** The venue's place name in the reader's script: the city as the host wrote it when it matches the language,
 *  else the zone's own city (English) or the local name for that time zone (Arabic). */
function zoneName(m, lang, t) {
  const arabicCity = /[\u0600-\u06FF]/.test(m.city);
  if (m.city && arabicCity === (lang === "ar")) return t("com.city_time", { city: m.city });
  if (lang !== "ar") return t("com.city_time", { city: m.tz.split("/").pop().replace(/_/g, " ") });
  try {
    const part = new Intl.DateTimeFormat("ar", { timeZone: m.tz, timeZoneName: "shortGeneric" })
      .formatToParts(new Date()).find((p) => p.type === "timeZoneName");
    if (part && /[\u0600-\u06FF]/.test(part.value)) return part.value.startsWith("توقيت") ? `ب${part.value}` : part.value;
  } catch { /* fall through */ }
  return t("com.city_time", { city: m.city });
}

function countdown(ms, lang) {
  const rtf = new Intl.RelativeTimeFormat(lang === "ar" ? "ar-SA-u-nu-arab" : "en-GB", { numeric: "auto" });
  const min = Math.round(ms / 60000);
  if (min < 60) return rtf.format(Math.max(1, min), "minute");
  if (min < 24 * 60) return rtf.format(Math.round(min / 60), "hour");
  return rtf.format(Math.round(min / (24 * 60)), "day");
}

/** When a meetup is, as the cards show it: the date, a countdown, and whether it is on now or over. */
export function useWhen(m) {
  const { t, lang, fmtDate } = useI18n();
  const zone = zoneOf(m);
  const start = new Date(m.starts_at).getTime();
  const end = start + m.duration_min * 60000;
  const now = Date.now();
  const away = zone.timeZone && zone.timeZone !== VIEWER_TZ;
  return {
    day: fmtDate(m.starts_at, { day: "numeric", ...zone }),
    month: fmtDate(m.starts_at, { month: "short", ...zone }),
    date: fmtDate(m.starts_at, { weekday: "long", day: "numeric", month: "long", ...zone }),
    time: fmtDate(m.starts_at, { hour: "numeric", minute: "2-digit", ...zone }) + (away ? ` (${zoneName(m, lang, t)})` : ""),
    countdown: now < start ? countdown(start - now, lang) : "",
    soon: now < start && start - now <= 15 * 60000,
    live: now >= start && now < end,
    ended: now >= end,
  };
}

export const placeOf = (m, lang) => [m.venue, m.city, countryName(m.country, lang)].filter(Boolean).join(lang === "ar" ? "، " : ", ");

/** Date, place and host: shown on the booking sheet so the seeker knows what they are booking. */
function MeetupSummary({ m }) {
  const { t, lang, fmtNum } = useI18n();
  const w = useWhen(m);
  return (
    <ul className="meta-list rsvp-summary">
      <li><Icon name="clock" size={16} />{w.date} · {w.time} · {t("com.minutes", { n: fmtNum(m.duration_min) })}</li>
      <li>{m.format === "online"
        ? <><Icon name="globe" size={16} />{t("com.online_place")}</>
        : <><Icon name="pin" size={16} /><span dir="auto">{placeOf(m, lang)}</span></>}</li>
      {m.host && <li><Icon name="users" size={16} />{t("com.host", { name: m.host.name })}</li>}
    </ul>
  );
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

function RsvpForm({ meetup, onDone, account, close }) {
  const { t, lang } = useI18n();
  const open = meetup.registration === "open";
  const online = meetup.format === "online";
  const [nick, setNick] = useState(account ? account.username : open ? t("com.guest") : "");
  const [confirm, setConfirm] = useState(false);
  const [booked, setBooked] = useState(null);     // the meetup as returned after booking
  const [busy, setBusy] = useState(false);
  const forKids = meetup.age_group === "kids";
  const needsConfirm = forKids || needsAudience(meetup.audience);
  if (booked) return <Booked m={booked} close={close} />;
  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      setBooked(await api.post(`/api/meetups/${meetup.id}/rsvp?ui=${lang}`, { nickname: nick, confirm_audience: confirm }));
      onDone?.();
    } catch (err) {
      toast(errorText(err, t), "error");
      setBusy(false);
    }
  };
  return (
    <form className="stack" onSubmit={submit}>
      <MeetupSummary m={meetup} />
      <p className="small muted">{t(online ? "com.rsvp_note_online" : open ? "com.rsvp_note_open" : "com.rsvp_note")}</p>
      <div className="field">
        <label htmlFor="rsvp-nick">{t("com.nickname")}</label>
        <input id="rsvp-nick" className="input" maxLength={24} autoComplete="off" value={nick} onChange={(e) => setNick(e.target.value)} />
      </div>
      {needsConfirm && (
        <label className="check"><input type="checkbox" checked={confirm} onChange={(e) => setConfirm(e.target.checked)} />
          <span>{forKids ? t("com.confirm_guardian") : t("com.confirm_aud", { aud: t(audienceKey(meetup.audience)) })}</span></label>
      )}
      <div className="row"><button type="submit" className="btn btn-primary" disabled={busy || nick.trim().length < 2 || (needsConfirm && !confirm)}>
        <Icon name="check" />{t(open ? "com.confirm_join" : "com.confirm_booking")}
      </button></div>
    </form>
  );
}

/** After booking: what to do next (show the code, just come, or open the link) and where to find it again. */
function Booked({ m, close }) {
  const { t } = useI18n();
  const online = m.format === "online";
  const open = m.registration === "open";
  const code = !online && !open && m.my_rsvp ? m.my_rsvp.code : "";
  return (
    <div className="stack center booked">
      <p className="booked-check"><Icon name="check" size={30} /></p>
      <h3>{t(open ? "com.joined_title" : "com.booked")}</h3>
      {code && <><p className="muted">{t("com.code")}</p><p className="booking-code">{code}</p></>}
      <p className="small muted">{t(online ? "com.next_online" : code ? "com.next_code" : "com.next_open")}</p>
      {online && m.online_url && (
        <a className="btn btn-accent" href={m.online_url} target="_blank" rel="noopener noreferrer"><Icon name="external" />{t("com.open_link")}</a>
      )}
      <div className="row booked-actions">
        <a className="btn" href={`/api/meetups/${m.id}/ics`} download><Icon name="calendar" />{t("com.add_cal")}</a>
        <button type="button" className="btn btn-primary" onClick={() => { close(); navigate("/community?tab=mine"); }}>
          <Icon name="arrow" />{t("com.see_mine")}
        </button>
      </div>
    </div>
  );
}

export function openRsvp(meetup, t, onDone, account = null) {
  const title = t(meetup.registration === "open" ? "com.join_title_event" : "com.rsvp_title", { title: meetup.title });
  openSheet({ title, render: (close) => <RsvpForm meetup={meetup} onDone={onDone} account={account} close={close} /> });
}
