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

/** "Your call with X is at 6:30 PM" with a Join button, from 15 minutes before a booked call until it can't be joined. */
export function BookingBanner() {
  const { t, lang, fmtTime } = useI18n();
  const { account } = useAccount();
  const { path } = useHashPath();
  const [next, setNext] = useState(null);
  const [now, setNow] = useState(Date.now());
  usePolling(async () => {
    const data = await api.get("/api/bookings");
    setNext(data.upcoming[0] || null);
    setNow(Date.now());
  }, 60000, [account?.username], Boolean(account));
  useEffect(() => { const id = setInterval(() => setNow(Date.now()), 20000); return () => clearInterval(id); }, []);
  if (!account || !next || path === "/talk") return null;
  const start = new Date(next.starts_at).getTime();
  if (start - now > SOON || (!next.can_join && start < now)) return null;
  const name = next.daai ? (lang === "ar" ? next.daai.name : next.daai.name_en || next.daai.name) : "";
  const open = now >= start - 5 * 60 * 1000;
  return (
    <div className="booking-banner" role="status">
      <div className="booking-banner-inner">
        <Icon name="calendar" />
        <span>{open ? t("book.banner_now", { name }) : t("book.banner", { name, time: fmtTime(next.starts_at) })}</span>
        <a className="btn btn-sm btn-primary" href={`#/talk?booking=${next.id}`}>{open ? t("book.join") : t("book.my")}</a>
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
