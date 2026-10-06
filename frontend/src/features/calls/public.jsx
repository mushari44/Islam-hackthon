// What other features may use from Calls. Owner: Eman.
// RAG's "Talk to a da'i about this" button calls startReferral({lang, t, conversationId}); the da'i console uses CallPanel.
// useConversationCalls() gives the Ask page's chat list which da'i the seeker talked to about each chat.
// The shell shows <BookingBanner /> on every page: a reminder from 15 minutes before a booked call.
import "./strings.js";
import { useEffect, useState } from "react";
import { api } from "../../core/api.js";
import { useI18n } from "../../core/i18n.jsx";
import { useHashPath } from "../../core/router.jsx";
import { Icon, openSheet, usePolling } from "../../core/ui.jsx";
import { useAccount } from "../account/public.js";
import ReferralSheet from "./ReferralSheet.jsx";

const SOON = 15 * 60 * 1000;
const SEEN = "sabeeli.booking_notices";   // da'i cancellations this browser has already shown
const seen = () => { try { return JSON.parse(localStorage.getItem(SEEN) || "[]"); } catch { return []; } };
const markSeen = (id) => { try { localStorage.setItem(SEEN, JSON.stringify([...seen(), id].slice(-50))); } catch { /* private mode */ } };

/**
 * A strip under the top bar, on every page, for a signed-in seeker:
 * - from 15 minutes before a booked call: "Your call with X is at 6:30 PM", then "Join" once it opens;
 * - when a da'i cancelled one of their bookings (there is no email): what happened, with "Book another time".
 * Hidden on the Talk page while it already shows the booking (its waiting room or My bookings).
 */
export function BookingBanner() {
  const { t, lang, fmtTime, fmtDate } = useI18n();
  const { account } = useAccount();
  const { path, query } = useHashPath();
  const [data, setData] = useState(null);
  const [now, setNow] = useState(Date.now());
  const [dismissed, setDismissed] = useState(seen);
  usePolling(async () => {
    setData(await api.get("/api/bookings"));
    setNow(Date.now());
  }, 60000, [account?.username, path], Boolean(account));   // also re-checked on every page change
  useEffect(() => { const id = setInterval(() => setNow(Date.now()), 20000); return () => clearInterval(id); }, []);
  if (!account || !data) return null;
  if (path === "/talk" && (query.booking || query.mode === "bookings")) return null;
  const nameOf = (b) => (b.daai ? (lang === "ar" ? b.daai.name : b.daai.name_en || b.daai.name) : "");

  const next = data.upcoming[0];
  const start = next ? new Date(next.starts_at).getTime() : 0;
  if (next && start - now <= SOON && (next.can_join || start >= now)) {
    const open = now >= start - 5 * 60 * 1000;
    return (
      <div className="booking-banner" role="status">
        <div className="booking-banner-inner">
          <Icon name="calendar" />
          <span>{open ? t("book.banner_now", { name: nameOf(next) }) : t("book.banner", { name: nameOf(next), time: fmtTime(next.starts_at) })}</span>
          <a className="btn btn-sm btn-primary" href={`#/talk?booking=${next.id}`}>{open ? t("book.join") : t("book.my")}</a>
        </div>
      </div>
    );
  }
  const cancelled = data.past.find((b) => b.status === "cancelled" && b.cancelled_by !== "seeker" && !dismissed.includes(b.id)
    && new Date(b.starts_at).getTime() > now - 24 * 3600 * 1000);
  if (!cancelled) return null;
  const close = () => { markSeen(cancelled.id); setDismissed(seen()); };
  return (
    <div className="booking-banner is-warn" role="status">
      <div className="booking-banner-inner">
        <Icon name="alert" />
        <span>
          {t(cancelled.cancelled_by === "daai" ? "book.banner_cancelled" : "book.banner_cancelled_system",
            { name: nameOf(cancelled), when: `${fmtDate(cancelled.starts_at, { weekday: "long", day: "numeric", month: "long" })} · ${fmtTime(cancelled.starts_at)}` })}
          {cancelled.cancel_note && <span className="faint" dir="auto"> «{cancelled.cancel_note}»</span>}
        </span>
        <a className="btn btn-sm btn-primary" href="#/talk?mode=book" onClick={close}>{t("book.another")}</a>
        <button type="button" className="icon-btn" aria-label={t("common.close")} title={t("common.close")} onClick={close}><Icon name="x" size={16} /></button>
      </div>
    </div>
  );
}

export { default as CallPanel } from "./CallPanel.jsx";

export function startReferral({ lang, t, conversationId = null }) {
  return openSheet({ title: t("ref.title"), render: (close) => <ReferralSheet lang={lang} conversationId={conversationId} close={close} /> });
}

/** {conversationId: [{daai: {id, name, name_en, callable}, at, lang}]}, newest call first. Reloads when `key` changes. */
export function useConversationCalls(key) {
  const [byConv, setByConv] = useState({});
  useEffect(() => {
    let alive = true;
    api.get("/api/calls/conversations").then((rows) => {
      if (!alive) return;
      const out = {};
      for (const r of rows) (out[r.conversation_id] ||= []).push(r);
      setByConv(out);
    }).catch(() => {});
    return () => { alive = false; };
  }, [key]);
  return byConv;
}
