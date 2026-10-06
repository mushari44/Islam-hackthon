// Small helpers for booked calls: local dates, the viewer's time zone, and "add to calendar". Owner: Eman (calls).

/** "2026-10-07" for an ISO time, as a date in the viewer's own time zone. */
export function localDay(iso) {
  const d = new Date(iso);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

/** The next `n` local dates, starting today, as "YYYY-MM-DD". */
export function nextDays(n) {
  const out = [];
  const d = new Date();
  for (let i = 0; i < n; i += 1) {
    out.push(localDay(d.toISOString()));
    d.setDate(d.getDate() + 1);
  }
  return out;
}

/** Noon on a local date, as ISO, so formatting it never slips to the day before or after. */
export const dayIso = (day) => new Date(`${day}T12:00:00`).toISOString();

/** The viewer's time zone in words ("Arabian Standard Time"), or its IANA name. */
export function zoneName(lang) {
  try {
    const loc = lang === "ar" ? "ar-SA" : "en-GB";
    const part = new Intl.DateTimeFormat(loc, { timeZoneName: "long" }).formatToParts(new Date()).find((p) => p.type === "timeZoneName");
    return part ? part.value : Intl.DateTimeFormat().resolvedOptions().timeZone;
  } catch { return ""; }
}

export function browserZone() {
  try { return Intl.DateTimeFormat().resolvedOptions().timeZone || ""; } catch { return ""; }
}

/** Morning, afternoon or evening, by the viewer's local hour. */
export function period(iso) {
  const h = new Date(iso).getHours();
  return h < 12 ? "morning" : h < 17 ? "afternoon" : "evening";
}

const stamp = (iso) => new Date(iso).toISOString().replace(/[-:]/g, "").replace(/\.\d{3}/, "");
const link = (id) => `${window.location.origin}${window.location.pathname}#/talk?booking=${id}`;
const esc = (s) => String(s).replace(/[\\;,]/g, (c) => `\\${c}`).replace(/\n/g, "\\n");

/** A Google Calendar "new event" link with the booking filled in. */
export function googleCalendarUrl(b, title, details) {
  const q = new URLSearchParams({ action: "TEMPLATE", text: title, dates: `${stamp(b.starts_at)}/${stamp(b.ends_at)}`, details: `${details}\n${link(b.id)}` });
  return `https://calendar.google.com/calendar/render?${q}`;
}

/** Downloads an .ics file (Apple, Outlook and most calendars) with a reminder 15 minutes before. */
export function downloadIcs(b, title, details) {
  const text = [
    "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Sabeeli//Booked call//EN", "CALSCALE:GREGORIAN", "METHOD:PUBLISH",
    "BEGIN:VEVENT", `UID:sabeeli-booking-${b.id}@sabeeli`, `DTSTAMP:${stamp(new Date().toISOString())}`,
    `DTSTART:${stamp(b.starts_at)}`, `DTEND:${stamp(b.ends_at)}`, `SUMMARY:${esc(title)}`,
    `DESCRIPTION:${esc(`${details}\n${link(b.id)}`)}`, `URL:${link(b.id)}`,
    "BEGIN:VALARM", "TRIGGER:-PT15M", "ACTION:DISPLAY", `DESCRIPTION:${esc(title)}`, "END:VALARM",
    "END:VEVENT", "END:VCALENDAR", "",
  ].join("\r\n");
  const url = URL.createObjectURL(new Blob([text], { type: "text/calendar;charset=utf-8" }));
  const a = document.createElement("a");
  a.href = url;
  a.download = `sabeeli-call-${b.id}.ics`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
