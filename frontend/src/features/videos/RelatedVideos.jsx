// Related videos under an answer on the Ask page. Owner: Mushari.
// Suggestions only: they come from IslamHouse by topic, are never cited in the answer,
// and the question goes in a POST body so it never reaches server logs.
import "./strings.js";
import "./videos.css";
import { useEffect, useState } from "react";
import { api } from "../../core/api.js";
import { useI18n } from "../../core/i18n.jsx";
import { Icon } from "../../core/ui.jsx";
import { VideoCard } from "./cards.jsx";

const RETRY_MS = 4000;
const MAX_TRIES = 12;     // the first video list of a language takes ~30 s to build, then its videos are embedded

export default function RelatedVideos({ question, hints = [], lang }) {
  const { t } = useI18n();
  const [items, setItems] = useState([]);
  const [requested, setRequested] = useState(false);
  const [done, setDone] = useState(false);
  const hintKey = hints.join("|");

  useEffect(() => {
    let alive = true;
    let timer;
    let tries = 0;
    setItems([]);
    setDone(false);
    if (!question) return undefined;
    const load = () => {
      api.post("/api/videos/related", { lang, q: question, hints, k: 3 }, { as: "none" })
        .then((d) => {
          if (!alive) return;
          setItems(d.items || []);
          setRequested(Boolean(d.requested));
          if (d.state === "loading" && ++tries < MAX_TRIES) timer = setTimeout(load, RETRY_MS);
          else setDone(true);
        })
        .catch(() => { /* suggestions are optional */ });
    };
    load();
    return () => { alive = false; clearTimeout(timer); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [question, lang, hintKey]);

  if (!items.length) {
    // asked for a video and none is close enough: say so, and point to the videos page
    return requested && done ? (
      <p className="vid-related-none faint small"><Icon name="play" size={14} />{t("vid.related_none")}{" "}
        <a href="#/videos">{t("vid.related_browse")}</a></p>
    ) : null;
  }
  return (
    <section className="vid-related" aria-label={t("vid.related")}>
      <h4 className="vid-related-head"><Icon name="play" size={16} />{t("vid.related")}</h4>
      <div className="vid-related-row">
        {items.map((it) => <VideoCard key={it.id} item={it} compact />)}
      </div>
      <p className="faint small">{t("vid.related_note")}</p>
    </section>
  );
}
