// What other features may use from Calls. Owner: Eman.
// RAG's "Talk to a da'i about this" button calls startReferral({lang, t, conversationId}); the da'i console uses CallPanel.
// useConversationCalls() gives the Ask page's chat list which da'i the seeker talked to about each chat.
import { useEffect, useState } from "react";
import { api } from "../../core/api.js";
import { openSheet } from "../../core/ui.jsx";
import ReferralSheet from "./ReferralSheet.jsx";

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
