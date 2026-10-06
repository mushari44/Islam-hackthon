// App shell and routes. Shared core: features plug in through the route table below.
import { Suspense, lazy, useEffect, useState } from "react";
import { LangProvider, useI18n } from "./core/i18n.jsx";
import { match, useHashPath } from "./core/router.jsx";
import { Icon, Logo, SheetHost, ToastHost, usePageTitle } from "./core/ui.jsx";
import { AccountButton, AccountPage, useDaaiSignedIn } from "./features/account/index.js"; // Eman
import { BookingBanner, TalkPage } from "./features/calls/index.js";   // Eman
import { CommunityPage, GroupPage, MeetupPage } from "./features/community/index.js"; // Mushari
import { AskPage } from "./features/rag/index.js";                      // Mushari
import { VideosPage } from "./features/videos/index.js";               // Mushari
import Home from "./pages/Home.jsx";
import { About, More, NotFound, Privacy, Sources } from "./pages/Info.jsx";

// `title` names the page in the browser tab (a page with a data title, like a group, refines it with useTitle).
// Only da'is open the console: it loads on first visit instead of in every seeker's bundle.
const DaaiConsole = lazy(() => import("./features/daai/index.js").then((m) => ({ default: m.DaaiConsole }))); // Eman

const ROUTES = [
  { path: "/", nav: "home", page: Home, title: null },
  { path: "/ask", nav: "ask", page: AskPage, title: "ask.title" },
  { path: "/talk", nav: "talk", page: TalkPage, title: "nav.talk_long" },
  { path: "/community", nav: "community", page: CommunityPage, title: "nav.community" },
  { path: "/videos", nav: "videos", page: VideosPage, title: "vid.title" },
  { path: "/groups/:id", nav: "community", page: GroupPage, title: "nav.community" },
  { path: "/events/:id", nav: "community", page: MeetupPage, title: "nav.community" },
  { path: "/account", nav: "more", page: AccountPage, title: "nav.account" },
  { path: "/daai", nav: "more", page: DaaiConsole, title: "nav.daai" },
  { path: "/about", nav: "more", page: About, title: "nav.about" },
  { path: "/sources", nav: "more", page: Sources, title: "nav.sources" },
  { path: "/privacy", nav: "more", page: Privacy, title: "nav.privacy" },
  { path: "/more", nav: "more", page: More, title: "nav.more" },
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
  const daai = useDaaiSignedIn();
  let route = null;
  let params = {};
  for (const r of ROUTES) {
    const m = match(r.path, path);
    if (m) { route = r; params = m; break; }
  }
  const Page = route ? route.page : NotFound;
  const current = route ? route.nav : "more";

  const dataTitle = usePageTitle();
  const pageName = dataTitle || (route ? route.title && t(route.title) : t("nf.title"));
  useEffect(() => {
    const name = t("app.name");
    document.title = pageName ? `${pageName} · ${name}` : name;
  }, [pageName, t]);

  return (
    <>
      <a className="sr-only" href="#main" onClick={(e) => { e.preventDefault(); document.getElementById("main")?.focus(); }}>{t("common.skip")}</a>
      <header className="topbar">
        <div className="topbar-inner">
          <a className="brand" href="#/" aria-label={t("app.name")}>
            <Logo />
            <span className="brand-name">{t("app.name")}</span>
          </a>
          <nav className="nav" aria-label={t("nav.main_label")}>
            {NAV.map((n) => (
              <a key={n.key} href={n.href} aria-current={current === n.key ? "page" : undefined}><Icon name={n.icon} />
                {n.key === "talk"
                  ? <><span className="nav-long">{t("nav.talk_long")}</span><span className="nav-short">{t("nav.talk")}</span></>
                  : t(`nav.${n.key}`)}
              </a>
            ))}
          </nav>
          <div className="top-actions">
            <button type="button" className="btn btn-ghost btn-sm lang-btn" onClick={() => setLang(lang === "ar" ? "en" : "ar")} aria-label={t("common.lang_toggle")} lang={lang === "ar" ? "en" : "ar"}>
              <Icon name="globe" /><span className="btn-label">{t("common.lang_toggle")}</span><span className="btn-short" aria-hidden="true">{t("common.lang_short")}</span>
            </button>
            <button type="button" className="icon-btn" aria-label={t(isDark ? "common.theme_light" : "common.theme_dark")} title={t(isDark ? "common.theme_light" : "common.theme_dark")} onClick={() => setTheme(isDark ? "light" : "dark")}>
              <Icon name={isDark ? "sun" : "moon"} size={20} />
            </button>
            <AccountButton />
          </div>
        </div>
      </header>
      <BookingBanner />
      <main className="main" id="main" tabIndex={-1}>
        <Suspense fallback={<div className="skeleton" style={{ height: 160 }} />}>
          <Page key={path} params={params} query={query} theme={theme} setTheme={setTheme} />
        </Suspense>
      </main>
      <footer className="footer">
        <div className="footer-inner">
          <nav className="footer-links" aria-label={t("footer.links")}>
            <a href="#/about">{t("nav.about")}</a>
            <a href="#/sources">{t("nav.sources")}</a>
            <a href="#/privacy">{t("nav.privacy")}</a>
            <a href="#/daai">{t(daai ? "nav.daai" : "footer.daai")}</a>
          </nav>
          <p className="footer-note">{t("footer.ai")}</p>
          <p className="footer-note">© {t("app.name")} · {t("footer.challenge")}</p>
        </div>
      </footer>
      <nav className="tabbar" aria-label={t("nav.main_label")}>
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
