// App shell and routes. Shared core: features plug in through the route table below.
import { Suspense, lazy, useEffect, useState } from "react";
import { LangProvider, useI18n } from "./core/i18n.jsx";
import { match, useHashPath } from "./core/router.jsx";
import { Icon, Logo, SheetHost, ToastHost } from "./core/ui.jsx";
import { AccountButton, AccountPage } from "./features/account/index.js"; // Eman
import { TalkPage } from "./features/calls/index.js";                  // Eman
import { CommunityPage, GroupPage } from "./features/community/index.js"; // Mushari
import { AskPage } from "./features/rag/index.js";                      // Mushari
import { VideosPage } from "./features/videos/index.js";               // Mushari
import Home from "./pages/Home.jsx";
import { About, More, NotFound, Privacy, Sources } from "./pages/Info.jsx";

// Only da'is open the console: it loads on first visit instead of in every seeker's bundle.
const DaaiConsole = lazy(() => import("./features/daai/index.js").then((m) => ({ default: m.DaaiConsole }))); // Eman

const ROUTES = [
  { path: "/", nav: "home", page: Home },
  { path: "/ask", nav: "ask", page: AskPage },
  { path: "/talk", nav: "talk", page: TalkPage },
  { path: "/community", nav: "community", page: CommunityPage },
  { path: "/videos", nav: "videos", page: VideosPage },
  { path: "/groups/:id", nav: "community", page: GroupPage },
  { path: "/account", nav: "more", page: AccountPage },
  { path: "/daai", nav: "more", page: DaaiConsole },
  { path: "/about", nav: "more", page: About },
  { path: "/sources", nav: "more", page: Sources },
  { path: "/privacy", nav: "more", page: Privacy },
  { path: "/more", nav: "more", page: More },
];

const NAV = [
  { key: "home", href: "#/", icon: "home" },
  { key: "ask", href: "#/ask", icon: "ask" },
  { key: "talk", href: "#/talk", icon: "talk" },
  { key: "community", href: "#/community", icon: "community" },
  { key: "videos", href: "#/videos", icon: "play" },
];

function useTheme() {
  const [theme, setThemeState] = useState(() => { try { return localStorage.getItem("sabeeli.theme") || "auto"; } catch { return "auto"; } });
  useEffect(() => {
    if (theme === "auto") document.documentElement.removeAttribute("data-theme");
    else document.documentElement.setAttribute("data-theme", theme);
    try { localStorage.setItem("sabeeli.theme", theme); } catch { /* ignore */ }
  }, [theme]);
  const isDark = theme === "dark" || (theme === "auto" && window.matchMedia("(prefers-color-scheme: dark)").matches);
  return { theme, setTheme: setThemeState, isDark };
}

function Shell() {
  const { t, lang, setLang } = useI18n();
  const { path, query } = useHashPath();
  const { theme, setTheme, isDark } = useTheme();
  let route = null;
  let params = {};
  for (const r of ROUTES) {
    const m = match(r.path, path);
    if (m) { route = r; params = m; break; }
  }
  const Page = route ? route.page : NotFound;
  const current = route ? route.nav : "more";

  useEffect(() => {
    const h1 = document.querySelector("main h1");
    const name = t("app.name");
    document.title = h1 && h1.textContent !== name ? `${h1.textContent} · ${name}` : name;
  });

  return (
    <>
      <a className="sr-only" href="#main" onClick={(e) => { e.preventDefault(); document.getElementById("main")?.focus(); }}>{t("common.skip")}</a>
      <header className="topbar">
        <div className="topbar-inner">
          <a className="brand" href="#/" aria-label={t("app.name")}>
            <Logo />
            <span className="brand-name">{t("app.name")}</span>
          </a>
          <nav className="nav" aria-label="main">
            {NAV.map((n) => (
              <a key={n.key} href={n.href} aria-current={current === n.key ? "page" : undefined}><Icon name={n.icon} />{t(`nav.${n.key}`)}</a>
            ))}
          </nav>
          <div className="top-actions">
            <a className="btn btn-ghost btn-sm hide-mobile" href="#/daai" aria-current={path.startsWith("/daai") ? "page" : undefined}
              aria-label={t("nav.daai")} title={t("nav.daai")}><Icon name="users" /><span className="btn-label">{t("nav.daai")}</span></a>
            <button type="button" className="btn btn-ghost btn-sm lang-btn" onClick={() => setLang(lang === "ar" ? "en" : "ar")} aria-label={t("common.lang_toggle")} lang={lang === "ar" ? "en" : "ar"}>
              <Icon name="globe" /><span className="btn-label">{t("common.lang_toggle")}</span><span className="btn-short" aria-hidden="true">{t("common.lang_short")}</span>
            </button>
            <button type="button" className="icon-btn" aria-label={t("common.theme")} title={t("common.theme")} onClick={() => setTheme(isDark ? "light" : "dark")}>
              <Icon name={isDark ? "sun" : "moon"} size={20} />
            </button>
            <AccountButton />
          </div>
        </div>
      </header>
      <main className="main" id="main" tabIndex={-1}>
        <Suspense fallback={<div className="skeleton" style={{ height: 160 }} />}>
          <Page key={path} params={params} query={query} theme={theme} setTheme={setTheme} />
        </Suspense>
      </main>
      <footer className="footer">
        <div className="footer-inner">
          <span>{t("footer.ai")}</span>
          <a href="#/about">{t("nav.about")}</a>
          <a href="#/sources">{t("nav.sources")}</a>
          <a href="#/privacy">{t("nav.privacy")}</a>
          <span>{t("footer.challenge")}</span>
        </div>
      </footer>
      <nav className="tabbar" aria-label="tabs">
        {[...NAV, { key: "more", href: "#/more", icon: "more" }].map((n) => (
          <a key={n.key} href={n.href} aria-current={current === n.key ? "page" : undefined}><Icon name={n.icon} size={22} /><span>{t(`nav.${n.key}`)}</span></a>
        ))}
      </nav>
      <SheetHost />
      <ToastHost />
    </>
  );
}

export default function App() {
  return <LangProvider><Shell /></LangProvider>;
}
