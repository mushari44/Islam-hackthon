// One event's own page (#/events/:id), so an event can be linked, shared and bookmarked. Owner: Mushari (community).
import "./strings.js";
import "./community.css";
import { useEffect, useState } from "react";
import { api } from "../../core/api.js";
import { useI18n } from "../../core/i18n.jsx";
import { Icon, errorText, useTitle } from "../../core/ui.jsx";
import { useAccount } from "../account/public.js";
import { MeetupCard } from "./cards.jsx";

export default function MeetupPage({ params }) {
  const { t, lang } = useI18n();
  const { account } = useAccount();
  const mid = Number(params.id);
  const [m, setM] = useState(null);
  const [error, setError] = useState(null);
  useTitle(m?.title);
  const load = () => { setError(null); return api.get(`/api/meetups/${mid}?ui=${lang}`).then(setM).catch(setError); };
  useEffect(() => { load(); }, [mid, lang, account]); // eslint-disable-line react-hooks/exhaustive-deps
  const back = (
    <a className="btn btn-ghost btn-sm" href="#/community?tab=meetups"><Icon name="arrow" className="icon-back" />{t("ev.back")}</a>
  );
  if (error) {
    const transient = !error.status || error.status >= 500;
    return (
      <div className="empty">
        <p>{error.status === 404 ? t("ev.not_found") : errorText(error, t)}</p>
        <div className="row com-empty-actions">
          {back}
          {transient && <button type="button" className="btn btn-ghost btn-sm" onClick={load}>{t("common.retry")}</button>}
        </div>
      </div>
    );
  }
  if (!m) return <div className="skeleton" style={{ height: 220 }} />;
  return (
    <>
      {back}
      <h1 className="sr-only">{m.title}</h1>
      <div className="meetup-page"><MeetupCard m={m} reload={load} account={account} full /></div>
    </>
  );
}
