// Pieces shared inside the community feature: rules, join and RSVP forms. Owner: Mushari.
import "./strings.js";
import "./community.css";
import { useEffect, useState } from "react";
import { api, apiUrl } from "../../core/api.js";
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

// Each country's IANA time zones, the usual one first, so a da'i enters the time as it is at the venue.
export const COUNTRY_ZONES = {
  SA: ["Asia/Riyadh"], AE: ["Asia/Dubai"], KW: ["Asia/Kuwait"], QA: ["Asia/Qatar"], BH: ["Asia/Bahrain"], OM: ["Asia/Muscat"],
  EG: ["Africa/Cairo"], JO: ["Asia/Amman"], MA: ["Africa/Casablanca"], DZ: ["Africa/Algiers"], TN: ["Africa/Tunis"],
  IQ: ["Asia/Baghdad"], GB: ["Europe/London"], IE: ["Europe/Dublin"], DE: ["Europe/Berlin"], FR: ["Europe/Paris"],
  NL: ["Europe/Amsterdam"], SE: ["Europe/Stockholm"], TR: ["Europe/Istanbul"], MY: ["Asia/Kuala_Lumpur"],
  SG: ["Asia/Singapore"], PH: ["Asia/Manila"], NG: ["Africa/Lagos"], KE: ["Africa/Nairobi"], ZA: ["Africa/Johannesburg"],
  US: ["America/New_York", "America/Chicago", "America/Denver", "America/Phoenix", "America/Los_Angeles", "America/Anchorage", "Pacific/Honolulu"],
  CA: ["America/Toronto", "America/Halifax", "America/St_Johns", "America/Winnipeg", "America/Regina", "America/Edmonton", "America/Vancouver"],
  AU: ["Australia/Sydney", "Australia/Brisbane", "Australia/Adelaide", "Australia/Darwin", "Australia/Perth", "Australia/Hobart"],
  ID: ["Asia/Jakarta", "Asia/Makassar", "Asia/Jayapura"],
};

export const VIEWER_TZ = (() => { try { return Intl.DateTimeFormat().resolvedOptions().timeZone; } catch { return ""; } })();

/** Wall-clock parts of a moment in a time zone ({} = the viewer's own). */
function partsIn(ms, zone) {
  const parts = new Intl.DateTimeFormat("en-US", { ...zone, hourCycle: "h23", year: "numeric", month: "numeric", day: "numeric",
    hour: "numeric", minute: "numeric", second: "numeric" }).formatToParts(ms);
  return Object.fromEntries(parts.filter((p) => p.type !== "literal").map((p) => [p.type, Number(p.value)]));
}

/** The UTC ISO time of a `datetime-local` value ("2030-06-01T19:00") read as wall-clock time in `tz`. */
export function zonedToUtc(local, tz) {
  const [date, time] = local.split("T");
  const [y, mo, d] = date.split("-").map(Number);
  const [h, mi] = time.split(":").map(Number);
  const wall = Date.UTC(y, mo - 1, d, h, mi);
  const offset = (ms) => { const p = partsIn(ms, { timeZone: tz }); return Date.UTC(p.year, p.month - 1, p.day, p.hour % 24, p.minute, p.second) - ms; };
  const guess = wall - offset(wall);
  return new Date(wall - offset(guess)).toISOString();   // second pass: right on either side of a clock change
}

/** A time zone's city in the reader's language: named in strings for countries with several zones, else the
 *  country (Arabic) or the zone's own city (English). */
function zoneCity(tz, country, lang, t) {
  const key = `com.zone.${tz}`;
  const named = t(key);
  if (named !== key) return named;
  if (lang === "ar") return country ? countryName(country, "ar") : "";
  return tz.split("/").pop().replace(/_/g, " ");
}

/** A time zone's name for a picker or a note, e.g. "Eastern Time (New York)". */
export function zoneLabel(tz, lang, t) {
  const city = zoneCity(tz, "", lang, t);
  try {
    const name = new Intl.DateTimeFormat(lang, { timeZone: tz, timeZoneName: "longGeneric" }).formatToParts(new Date())
      .find((p) => p.type === "timeZoneName")?.value;
    if (name) return city ? `${name} (${city})` : name;
  } catch { /* fall through */ }
  return city || tz;
}

// One clock for every card, so countdowns, "Join now" and "Happening now" move on their own.
const ticks = new Set();
let ticker = null;
export function useNow() {
  const [now, setNow] = useState(Date.now);
  useEffect(() => {
    const tick = () => setNow(Date.now());
    ticks.add(tick);
    if (!ticker) ticker = setInterval(() => ticks.forEach((f) => f()), 30000);
    return () => {
      ticks.delete(tick);
      if (!ticks.size) { clearInterval(ticker); ticker = null; }
    };
  }, []);
  return now;
}

/** Intl options showing an in-person meetup in its venue's time zone; an online one shows in the viewer's own. */
function zoneOf(m) {
  if (m.format === "online" || !m.tz) return {};
  try { new Intl.DateTimeFormat("en", { timeZone: m.tz }); return { timeZone: m.tz }; } catch { return {}; }
}

const ARABIC = /[\u0600-\u06FF]/;

/** "(London time)": the venue's place in the reader's script, the city as the host wrote it when it is in that
 *  script, else the zone's city or country. */
function zoneName(m, lang, t) {
  const city = m.city && ARABIC.test(m.city) === (lang === "ar") ? m.city : zoneCity(m.tz, m.country, lang, t);
  return t("com.city_time", { city: city || m.city });
}

/** "in 20 minutes", "in 5 hours", "tomorrow", "in 3 days": days count calendar days where the meetup is shown. */
function countdown(start, now, zone, lang) {
  const rtf = new Intl.RelativeTimeFormat(lang === "ar" ? "ar-SA-u-nu-arab" : "en-GB", { numeric: "auto" });
  const min = Math.floor((start - now) / 60000);
  if (min < 60) return rtf.format(Math.max(1, min), "minute");
  const day = (ms) => { const p = partsIn(ms, zone); return Date.UTC(p.year, p.month - 1, p.day) / 86400000; };
  const days = day(start) - day(now);
  if (days === 0 || min < 6 * 60) return rtf.format(Math.floor(min / 60), "hour");
  return rtf.format(days, "day");
}

/** When a meetup is, as the cards show it: the date, a countdown, and whether it is on now or over. */
export function useWhen(m) {
  const { t, lang, fmtDate } = useI18n();
  const now = useNow();
  const zone = zoneOf(m);
  const start = new Date(m.starts_at).getTime();
  const end = start + m.duration_min * 60000;
  const away = zone.timeZone && zone.timeZone !== VIEWER_TZ;
  return {
    day: fmtDate(m.starts_at, { day: "numeric", ...zone }),
    month: fmtDate(m.starts_at, { month: "short", ...zone }),
    date: fmtDate(m.starts_at, { weekday: "long", day: "numeric", month: "long", ...zone }),
    time: fmtDate(m.starts_at, { hour: "numeric", minute: "2-digit", ...zone }) + (away ? ` (${zoneName(m, lang, t)})` : ""),
    countdown: now < start ? countdown(start, now, zone, lang) : "",
    soon: now < start && start - now <= 15 * 60000,
    live: now >= start && now < end,
    ended: now >= end,
  };
}

export const placeOf = (m, lang) => [m.venue, m.city, countryName(m.country, lang)].filter(Boolean).join(lang === "ar" ? "، " : ", ");

/** Date, place and host: shown on the booking sheet so the seeker knows what they are booking. */
function MeetupSummary({ m }) {
  const { t, tn, lang } = useI18n();
  const w = useWhen(m);
  return (
    <ul className="meta-list rsvp-summary">
      <li><Icon name="clock" size={16} />{w.date} · {w.time} · {tn("com.minutes", m.duration_min)}</li>
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

/**
 * Joining, posting and booking a seat need a free account (as on common community sites). A signed-out seeker
 * sees this instead of the form; signing in brings them back to `next`, which reopens the form.
 */
function SignInFirst({ next, what }) {
  const { t } = useI18n();
  return (
    <div className="stack">
      <p className="muted">{t(what === "join" ? "com.need_account_join" : "com.need_account_rsvp")}</p>
      <div className="row">
        <a className="btn btn-primary" href={`#/account?next=${encodeURIComponent(next)}`}><Icon name="lock" />{t("com.signin_or_create")}</a>
      </div>
    </div>
  );
}

/** The join form, or the sign-in step for a signed-out seeker. */
function JoinGate({ group, close, onJoined }) {
  const { account, loaded } = useAccount();
  if (!loaded) return null;
  if (!account) return <SignInFirst what="join" next={`/groups/${group.id}?join=1`} />;
  return <JoinForm group={group} close={close} onJoined={onJoined} />;
}

export function openJoin(group, t, onJoined) {
  openSheet({ title: t("com.join_title", { title: group.title }), render: (close) => <JoinGate group={group} close={close} onJoined={onJoined} /> });
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
        <a className="btn" href={apiUrl(`/api/meetups/${m.id}/ics`)} download><Icon name="calendar" />{t("com.add_cal")}</a>
        <button type="button" className="btn btn-primary" onClick={() => { close(); navigate("/community?tab=mine"); }}>
          <Icon name="arrow" className="icon-go" />{t("com.see_mine")}
        </button>
      </div>
    </div>
  );
}

function RsvpGate({ meetup, onDone, close }) {
  const { account, loaded } = useAccount();
  if (!loaded) return null;
  if (!account) return <SignInFirst what="rsvp" next={`/events/${meetup.id}?rsvp=1`} />;
  return <RsvpForm meetup={meetup} onDone={onDone} account={account} close={close} />;
}

export function openRsvp(meetup, t, onDone) {
  const title = t(meetup.registration === "open" ? "com.join_title_event" : "com.rsvp_title", { title: meetup.title });
  openSheet({ title, render: (close) => <RsvpGate meetup={meetup} onDone={onDone} close={close} /> });
}
