// Da'i console, community tabs: lead and moderate groups; host meetups. Owner: Eman.
// The community API behind these screens is Mushari's (see docs/API.md, "Community").
import "./strings.js";
import { useEffect, useRef, useState } from "react";
import { api } from "../../core/api.js";
import { useI18n } from "../../core/i18n.jsx";
import { Icon, errorText, openSheet, toast, usePolling } from "../../core/ui.jsx";
import {
  AGE_GROUPS, COUNTRIES, COUNTRY_ZONES, FORMATS, GROUP_AGE_GROUPS, GroupMessage, REGISTRATION, SERIES, audienceKey, countryName, useWhen,
  zoneLabel, zonedToUtc,
} from "../community/public.js";

const DEVICE_TZ = (() => { try { return Intl.DateTimeFormat().resolvedOptions().timeZone; } catch { return ""; } })();
// A venue's time zone: the device's own when it is one of the country's, else the country's usual one.
const zonesOf = (country) => COUNTRY_ZONES[country] || [DEVICE_TZ].filter(Boolean);
const venueZone = (country) => (zonesOf(country).includes(DEVICE_TZ) ? DEVICE_TZ : zonesOf(country)[0] || "");

function Select({ id, name, value, onChange, options }) {
  return (
    <select id={id} className="select" name={name} value={value} onChange={(e) => onChange(e.target.value)}>
      {options.map(([v, label]) => <option key={v} value={v}>{label}</option>)}
    </select>
  );
}

function GroupForm({ close, onDone }) {
  const { t, lang, langName } = useI18n();
  const [f, setF] = useState({ title: "", description: "", lang: "ar", audience: "all", age_group: "all", city: "", country: "" });
  const set = (k) => (v) => setF({ ...f, [k]: typeof v === "string" ? v : v.target.value });
  const submit = async (e) => {
    e.preventDefault();
    try { await api.dPost("/api/daai/groups", f); close(); onDone(); } catch (err) { toast(errorText(err, t), "error"); }
  };
  return (
    <form className="stack" onSubmit={submit}>
      <div className="field"><label htmlFor="g-title">{t("dg.title")}</label><input id="g-title" className="input" required minLength={3} value={f.title} onChange={set("title")} /></div>
      <div className="field"><label htmlFor="g-desc">{t("dg.desc")}</label><textarea id="g-desc" className="textarea" rows={3} value={f.description} onChange={set("description")} /></div>
      <div className="grid grid-2">
        <div className="field"><label htmlFor="g-lang">{t("dg.lang")}</label><Select id="g-lang" value={f.lang} onChange={set("lang")} options={["ar", "en"].map((l) => [l, langName(l)])} /></div>
        <div className="field"><label htmlFor="g-aud">{t("dg.audience")}</label><Select id="g-aud" value={f.audience} onChange={set("audience")} options={["all", "women", "men"].map((a) => [a, t(audienceKey(a))])} /></div>
        <div className="field"><label htmlFor="g-city">{t("dg.city")}</label><input id="g-city" className="input" value={f.city} onChange={set("city")} /></div>
        <div className="field"><label htmlFor="g-country">{t("dg.country")}</label><Select id="g-country" value={f.country} onChange={set("country")} options={[["", "—"], ...COUNTRIES.map((c) => [c, countryName(c, lang)])]} /></div>
        <div className="field"><label htmlFor="g-age">{t("com.age")}</label><Select id="g-age" value={f.age_group} onChange={set("age_group")} options={GROUP_AGE_GROUPS.map((a) => [a, t(`com.age.${a}`)])} /></div>
      </div>
      <div className="row"><button type="submit" className="btn btn-primary">{t("dg.create")}</button></div>
    </form>
  );
}

function ManageGroup({ group, back }) {
  const { t } = useI18n();
  const [messages, setMessages] = useState([]);
  const [text, setText] = useState("");
  const lastId = useRef(0);
  const poll = async () => {
    const msgs = await api.dGet(`/api/groups/${group.id}/messages?after=${lastId.current}`);
    if (!msgs.length) return;
    lastId.current = Math.max(lastId.current, ...msgs.map((m) => m.id));
    setMessages((list) => [...list, ...msgs.filter((m) => !list.some((x) => x.id === m.id))]);
  };
  usePolling(poll, 3000, [group.id]);
  const patch = (id, change) => setMessages((list) => list.map((m) => (m.id === id ? { ...m, ...change } : m)));
  const post = async (e) => {
    e.preventDefault();
    if (!text.trim()) return;
    try { await api.dPost(`/api/daai/groups/${group.id}/messages`, { text }); setText(""); poll(); } catch (err) { toast(errorText(err, t), "error"); }
  };
  const tools = (m) => (
    <div className="row mod-tools">
      {!m.deleted && (
        <button type="button" className="btn btn-ghost btn-sm" onClick={() => api.dPost(`/api/daai/groups/${group.id}/messages/${m.id}/delete`, {}).then(() => patch(m.id, { deleted: true })).catch((err) => toast(errorText(err, t), "error"))}>
          <Icon name="trash" />{t("dg.delete")}
        </button>
      )}
      {m.author_type === "seeker" && m.member_id && (
        <button type="button" className="btn btn-ghost btn-sm" onClick={() => api.dPost(`/api/daai/groups/${group.id}/members/${m.member_id}/mute`, { muted: true }).then(() => toast(t("dg.muted_ok"))).catch((err) => toast(errorText(err, t), "error"))}>
          <Icon name="micOff" />{t("dg.mute")}
        </button>
      )}
      {m.needs_leader && !m.deleted && (
        <button type="button" className="btn btn-accent btn-sm" onClick={() => api.dPost(`/api/daai/groups/${group.id}/messages/${m.id}/resolve`, {}).then(() => patch(m.id, { needs_leader: false })).catch((err) => toast(errorText(err, t), "error"))}>
          <Icon name="check" />{t("dg.resolve")}
        </button>
      )}
    </div>
  );
  return (
    <div className="stack">
      <button type="button" className="btn btn-ghost btn-sm" style={{ alignSelf: "flex-start" }} onClick={back}><Icon name="arrow" className="icon-back" />{t("dg.back")}</button>
      <h3>{group.title}</h3>
      <div className="group-feed">{messages.map((m) => <GroupMessage key={m.id} m={m} tools={tools(m)} />)}</div>
      <form className="row" onSubmit={post}>
        <input className="input" style={{ flex: 1 }} maxLength={2000} placeholder={t("dg.post_ph")} value={text} onChange={(e) => setText(e.target.value)} />
        <button type="submit" className="btn btn-primary" aria-label={t("common.send")}><Icon name="send" /></button>
      </form>
    </div>
  );
}

function GroupsTab() {
  const { t, fmtNum, langName } = useI18n();
  const [groups, setGroups] = useState(null);
  const [open, setOpen] = useState(null);
  const load = () => api.dGet("/api/daai/groups").then(setGroups).catch((err) => toast(errorText(err, t), "error"));
  useEffect(() => { load(); }, []); // eslint-disable-line react-hooks/exhaustive-deps
  if (open) return <ManageGroup group={open} back={() => { setOpen(null); load(); }} />;
  return (
    <div className="stack">
      <div className="row spread">
        <h3>{t("dg.groups")}</h3>
        <button type="button" className="btn btn-accent btn-sm" onClick={() => openSheet({ title: t("dg.new"), render: (close) => <GroupForm close={close} onDone={load} /> })}>
          <Icon name="plus" />{t("dg.new")}
        </button>
      </div>
      {groups && groups.length === 0 && <p className="empty">{t("dg.empty")}</p>}
      <div className="grid grid-2">
        {(groups || []).map((g) => (
          <article className="card stack" key={g.id}>
            <div className="row">
              <span className="badge">{langName(g.lang)}</span>
              {g.needs_leader > 0 && <span className="badge badge-warn">{t("dg.flags", { n: fmtNum(g.needs_leader) })}</span>}
            </div>
            <h3>{g.title}</h3>
            <p className="faint">{t("com.members", { n: fmtNum(g.members) })}</p>
            <div className="row"><button type="button" className="btn btn-primary btn-sm" onClick={() => setOpen(g)}>{t("dg.open")}</button></div>
          </article>
        ))}
      </div>
    </div>
  );
}

function MeetupForm({ groups, close, onDone }) {
  const { t, lang, langName } = useI18n();
  const [f, setF] = useState({ title: "", description: "", venue: "", city: "", starts_at: "", duration_min: 90, capacity: 20,
    lang: "ar", country: "SA", audience: "all", registration: "required", age_group: "all", series: "", group_id: "", public_venue: false,
    format: "in_person", online_url: "", tz: venueZone("SA") });
  const online = f.format === "online";
  const set = (k) => (v) => setF({ ...f, [k]: typeof v === "object" && v.target ? v.target.value : v });
  // In person, the time is entered as it is at the venue; online, as it is on this device.
  const zone = online ? DEVICE_TZ : f.tz;
  const zones = zonesOf(f.country);
  const submit = async (e) => {
    e.preventDefault();
    const body = { ...f, starts_at: zone ? zonedToUtc(f.starts_at, zone) : new Date(f.starts_at).toISOString(),
      duration_min: Number(f.duration_min), capacity: Number(f.capacity), group_id: f.group_id ? Number(f.group_id) : null, tz: zone };
    try { await api.dPost("/api/daai/meetups", body); close(); onDone(); } catch (err) { toast(errorText(err, t), "error"); }
  };
  return (
    <form className="stack" onSubmit={submit}>
      <div className="field">
        <span className="field-label">{t("com.format")}</span>
        <div className="row" role="group" aria-label={t("com.format")}>
          {FORMATS.map((fm) => (
            <button key={fm} type="button" className="chip" aria-pressed={f.format === fm}
              onClick={() => setF({ ...f, format: fm, age_group: fm === "online" && f.age_group === "kids" ? "all" : f.age_group })}>
              <Icon name={fm === "online" ? "globe" : "pin"} size={16} />{t(`com.fmt.${fm}`)}
            </button>
          ))}
        </div>
      </div>
      <div className="field">
        <span className="field-label">{t("dm.kind")}</span>
        <div className="row" role="group" aria-label={t("dm.kind")}>
          {REGISTRATION.map((r) => (
            <button key={r} type="button" className="chip" aria-pressed={f.registration === r} onClick={() => setF({ ...f, registration: r })}>
              {t(`com.reg.${r}`)}
            </button>
          ))}
        </div>
        <span className="faint">{t(f.registration === "open" ? (online ? "dm.kind_open_online" : "dm.kind_open") : online ? "dm.kind_required_online" : "dm.kind_required")}</span>
      </div>
      <div className="field"><label htmlFor="m-title">{t("dg.title")}</label><input id="m-title" className="input" required minLength={3} value={f.title} onChange={set("title")} /></div>
      <div className="field"><label htmlFor="m-desc">{t("dg.desc")}</label><textarea id="m-desc" className="textarea" rows={2} value={f.description} onChange={set("description")} /></div>
      {online && (
        <div className="field">
          <label htmlFor="m-url">{t("com.online_url")}</label>
          <input id="m-url" className="input" type="url" required pattern="https://.+" placeholder="https://" dir="ltr" value={f.online_url} onChange={set("online_url")} />
          <span className="faint small">{t("com.online_url_hint")}</span>
        </div>
      )}
      <div className="grid grid-2">
        {!online && <>
          <div className="field"><label htmlFor="m-venue">{t("dm.venue")}</label><input id="m-venue" className="input" required value={f.venue} onChange={set("venue")} /></div>
          <div className="field"><label htmlFor="m-country">{t("dg.country")}</label><Select id="m-country" value={f.country} onChange={(c) => setF({ ...f, country: c, tz: venueZone(c) })} options={COUNTRIES.map((c) => [c, countryName(c, lang)])} /></div>
          <div className="field"><label htmlFor="m-city">{t("dg.city")}</label><input id="m-city" className="input" required value={f.city} onChange={set("city")} /></div>
        </>}
        <div className="field">
          <label htmlFor="m-when">{t("dm.when")}</label><input id="m-when" className="input" type="datetime-local" required value={f.starts_at} onChange={set("starts_at")} />
          {zone && <span className="faint small">{t(online ? "com.tz_note" : "com.tz_venue", { tz: zoneLabel(zone, lang, t) })}</span>}
        </div>
        {!online && zones.length > 1 && (
          <div className="field"><label htmlFor="m-tz">{t("com.tz_label")}</label><Select id="m-tz" value={f.tz} onChange={set("tz")} options={zones.map((z) => [z, zoneLabel(z, lang, t)])} /></div>
        )}
        <div className="field"><label htmlFor="m-dur">{t("dm.duration")}</label><input id="m-dur" className="input" type="number" min={15} max={480} value={f.duration_min} onChange={set("duration_min")} /></div>
        <div className="field"><label htmlFor="m-cap">{t(f.registration === "open" ? "dm.capacity_open" : "dm.capacity")}</label><input id="m-cap" className="input" type="number" min={2} max={500} value={f.capacity} onChange={set("capacity")} /></div>
        <div className="field"><label htmlFor="m-lang">{t("dg.lang")}</label><Select id="m-lang" value={f.lang} onChange={set("lang")} options={["ar", "en"].map((l) => [l, langName(l)])} /></div>
        <div className="field"><label htmlFor="m-aud">{t("dg.audience")}</label><Select id="m-aud" value={f.audience} onChange={set("audience")} options={["all", "women", "men", "families"].map((a) => [a, t(audienceKey(a))])} /></div>
        <div className="field"><label htmlFor="m-age">{t("com.age")}</label><Select id="m-age" value={f.age_group} onChange={set("age_group")} options={(online ? GROUP_AGE_GROUPS : AGE_GROUPS).map((a) => [a, t(`com.age.${a}`)])} /></div>
        <div className="field"><label htmlFor="m-series">{t("dm.series")}</label><Select id="m-series" value={f.series} onChange={set("series")} options={[["", t("dm.none")], ...SERIES.map((sr) => [sr, t(`com.series.${sr}`)])]} /></div>
        <div className="field"><label htmlFor="m-group">{t("dm.group")}</label><Select id="m-group" value={f.group_id} onChange={set("group_id")} options={[["", t("dm.none")], ...groups.map((g) => [String(g.id), g.title])]} /></div>
      </div>
      {f.age_group === "kids" && <p className="small muted">{t("dm.kids_note")}</p>}
      {!online && <label className="check"><input type="checkbox" checked={f.public_venue} onChange={(e) => setF({ ...f, public_venue: e.target.checked })} /><span>{t("dm.public")}</span></label>}
      <div className="row"><button type="submit" className="btn btn-primary" disabled={!online && !f.public_venue}>{t("dm.create")}</button></div>
    </form>
  );
}

/** Date, time and place of one of the da'i's meetups, in the venue's time zone; the link for an online one. */
function MeetupWhere({ m }) {
  const { t } = useI18n();
  const w = useWhen(m);
  return (
    <p className="faint">
      {w.date} · {w.time} · {m.format === "online"
        ? <>{t("com.fmt.online")}{m.online_url && <> · <a href={m.online_url} target="_blank" rel="noopener noreferrer" dir="ltr">{t("com.open_link")}</a></>}</>
        : <span dir="auto">{m.venue}</span>}
    </p>
  );
}

function MeetupsTab() {
  const { t, fmtNum, langName } = useI18n();
  const [data, setData] = useState({ meetups: [], groups: [] });
  const load = () => Promise.all([api.dGet("/api/daai/meetups"), api.dGet("/api/daai/groups")])
    .then(([meetups, groups]) => setData({ meetups, groups })).catch((err) => toast(errorText(err, t), "error"));
  useEffect(() => { load(); }, []); // eslint-disable-line react-hooks/exhaustive-deps
  return (
    <div className="stack">
      <div className="row spread">
        <h3>{t("dm.meetups")}</h3>
        <button type="button" className="btn btn-accent btn-sm"
          onClick={() => openSheet({ title: t("dm.new"), wide: true, render: (close) => <MeetupForm groups={data.groups} close={close} onDone={load} /> })}>
          <Icon name="plus" />{t("dm.new")}
        </button>
      </div>
      {data.meetups.length === 0 && <p className="empty">{t("dm.empty")}</p>}
      {data.meetups.map((m) => (
        <article className="card stack" key={m.id}>
          <div className="row">
            <span className="badge">{t(`com.fmt.${m.format === "online" ? "online" : "in_person"}`)}</span>
            <span className="badge">{langName(m.lang)}</span>
            <span className="badge badge-purple">{t(audienceKey(m.audience))}</span>
            {m.age_group !== "all" && <span className="badge">{t(`com.age.${m.age_group}`)}</span>}
            {m.series && <span className="badge badge-purple">{t(`com.series.${m.series}`)}</span>}
            {m.status === "cancelled" && <span className="badge badge-warn">{t("dm.cancelled")}</span>}
          </div>
          <h3 dir="auto">{m.title}</h3>
          <MeetupWhere m={m} />
          {m.registration === "open" ? <p className="walk-in">{t("com.walk_in")}</p> : <p className="reg-needed">{t("com.reg_needed")}</p>}
          {m.registration === "open" ? null : <details>
            <summary>{t("dm.attendees", { n: fmtNum(m.attendees.length) })}</summary>
            <ul>{m.attendees.map((n, i) => <li key={i}>{n}</li>)}</ul>
          </details>}
          {m.status === "open" && (
            <div className="row">
              <button type="button" className="btn btn-danger-soft btn-sm" onClick={() => api.dPost(`/api/daai/meetups/${m.id}/cancel`, {}).then(load).catch((err) => toast(errorText(err, t), "error"))}>
                <Icon name="x" />{t("dm.cancel")}
              </button>
            </div>
          )}
        </article>
      ))}
    </div>
  );
}

export const groupsTab = { key: "groups", labelKey: "dg.tab", component: GroupsTab };
export const meetupsTab = { key: "meetups", labelKey: "dm.tab", component: MeetupsTab };
