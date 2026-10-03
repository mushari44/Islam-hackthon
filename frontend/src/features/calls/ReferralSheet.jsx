// The referral card the seeker reviews, edits and chooses to share before a call. Owner: Eman (calls).
import "./strings.js";
import "./calls.css";
import { useEffect, useState } from "react";
import { api } from "../../core/api.js";
import { useI18n } from "../../core/i18n.jsx";
import { navigate } from "../../core/router.jsx";
import { Icon, Notice, Spinner, errorText, toast } from "../../core/ui.jsx";

function SourceChip({ id }) {
  const { lang } = useI18n();
  const [title, setTitle] = useState(id);
  useEffect(() => {
    api.pGet(`/api/sources/${encodeURIComponent(id)}?lang=${lang}`).then((c) => setTitle(c.title)).catch(() => {});
  }, [id, lang]);
  return <span className="badge">{title}</span>;
}

export default function ReferralSheet({ lang, conversationId, close }) {
  const { t, fmtNum } = useI18n();
  const [draft, setDraft] = useState(null);
  const [card, setCard] = useState(null);
  const [consent, setConsent] = useState(false);
  const [shareChat, setShareChat] = useState(false);
  const [sending, setSending] = useState(false);

  useEffect(() => {
    let alive = true;
    api.post("/api/referral/draft", { lang, conversation_id: conversationId || null })
      .then((d) => { if (alive) { setDraft(d); setCard({ ...d.card, explained: (d.card.explained || []).map((e) => ({ ...e })) }); } })
      .catch((err) => { toast(errorText(err, t), "error"); close(); });
    return () => { alive = false; };
  }, [lang]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!draft) return <Spinner label={t("ref.preparing")} />;

  const finish = async (withCard) => {
    setSending(true);
    try {
      await api.post(`/api/referral/${draft.id}/confirm`, { consent: withCard, card: withCard ? card : {}, share_chat: shareChat });
    } catch (err) {
      toast(errorText(err, t), "error");
      setSending(false);
      return;
    }
    close();
    // keep the referral id even without consent: it records the experiment arm (the da'i sees no card)
    navigate(`/talk?ref=${draft.id}&lang=${lang}${withCard ? "&card=1" : ""}${shareChat ? "&chat=1" : ""}`);
  };

  // Separate from the summary: the da'i sees this chat's questions and answers exactly as they are now.
  const chatOption = draft.chat_turns > 0 && (
    <div className="share-chat stack">
      <label className="check"><input type="checkbox" checked={shareChat} onChange={(e) => setShareChat(e.target.checked)} />
        <span>{t("ref.share_chat", { n: fmtNum(draft.chat_turns) })}</span></label>
      <p className="small muted">{t("ref.share_chat_hint")}</p>
    </div>
  );

  if (draft.mode === "none") {
    return (
      <div className="stack">
        <p>{t("ref.none")}</p>
        {chatOption}
        <div className="row"><button type="button" className="btn btn-primary" onClick={() => finish(false)}><Icon name="talk" />{t("ref.skip")}</button></div>
      </div>
    );
  }

  const set = (key) => (e) => setCard({ ...card, [key]: e.target.value });
  return (
    <div className="stack">
      <p className="muted">{t("ref.intro")}</p>
      <div className="row"><span className="badge badge-purple">{draft.mode === "model" ? t("ref.model") : t("ref.template")}</span></div>
      <div className="field"><label htmlFor="ref-q">{t("ref.question")}</label>
        <textarea id="ref-q" className="textarea" rows={3} dir="auto" value={card.question || ""} onChange={set("question")} /></div>
      <div className="field"><label htmlFor="ref-c">{t("ref.context")}</label>
        <textarea id="ref-c" className="textarea" rows={2} dir="auto" value={card.context || ""} onChange={set("context")} /></div>
      {card.explained.length > 0 && (
        <div className="field">
          <label>{t("ref.explained")}</label>
          <div className="stack">
            {card.explained.map((item, i) => (
              <div className="ref-point" key={i}>
                <textarea className="textarea" rows={2} dir="auto" value={item.point} aria-label={t("ref.explained")}
                  onChange={(e) => setCard({ ...card, explained: card.explained.map((x, j) => (j === i ? { ...x, point: e.target.value } : x)) })} />
                <div className="row">
                  {(item.sources || []).map((s) => <SourceChip key={s} id={s} />)}
                  <button type="button" className="btn btn-ghost btn-sm"
                    onClick={() => setCard({ ...card, explained: card.explained.filter((_, j) => j !== i) })}>
                    <Icon name="trash" />{t("ref.remove")}
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
      <div className="field"><label htmlFor="ref-u">{t("ref.unclear")}</label>
        <textarea id="ref-u" className="textarea" rows={2} dir="auto" value={card.unclear || ""} onChange={set("unclear")} /></div>
      <Notice icon="lock"><span className="small">{t("ref.private")}</span></Notice>
      <label className="check"><input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} /><span>{t("ref.consent")}</span></label>
      {chatOption}
      <div className="row">
        <button type="button" className="btn btn-primary" disabled={!consent || sending} onClick={() => finish(true)}><Icon name="talk" />{t("ref.share")}</button>
        <button type="button" className="btn btn-ghost" disabled={sending} onClick={() => finish(false)}>{t("ref.skip")}</button>
      </div>
    </div>
  );
}
