// Top bar entry, last in the bar: "Sign in" when signed out, "Da'i console" for a da'i, and for a seeker their username,
// which opens the usual account menu (my account, my activities, my chats, sign out). Owner: Eman.
// It also asks an older account that has no sex or age band yet to pick them, once per visit.
import "./strings.js";
import { useEffect, useRef, useState } from "react";
import { useI18n } from "../../core/i18n.jsx";
import { currentPath, useHashPath } from "../../core/router.jsx";
import { Icon, openSheet, toast } from "../../core/ui.jsx";
import { CompleteAbout, needsAbout } from "./fields.jsx";
import { signOutSeeker, useAccount, useDaaiSignedIn } from "./store.js";

let asked = false;   // once per page load: closing the question doesn't bring it straight back

export function AccountButton() {
  const { t } = useI18n();
  const { account } = useAccount();
  const { path } = useHashPath();
  const daaiOn = useDaaiSignedIn();
  const daai = !account && daaiOn;   // a seeker account comes first when both are signed in on this device
  const missing = needsAbout(account);
  useEffect(() => {
    if (!missing || asked || window.location.hash.startsWith("#/account")) return undefined;   // the account page asks itself
    asked = true;
    const timer = setTimeout(() => openSheet({ title: t("acc.complete_title"), render: (close) => <CompleteAbout account={account} close={close} /> }));
    return () => clearTimeout(timer);
  }, [missing]); // eslint-disable-line react-hooks/exhaustive-deps
  if (account) return <AccountMenu account={account} missing={missing} here={path.startsWith("/account")} />;
  // Signed out, the button opens the sign-in card (which /daai shows too, with "da'i" picked) and, from any other
  // page, brings the seeker back there afterwards.
  const back = ["/", "/account", "/daai"].includes(path) ? "" : `?next=${encodeURIComponent(currentPath())}`;
  const href = daai ? "#/daai" : `#/account${back}`;
  const here = daai ? path.startsWith("/daai") : path.startsWith("/account") || path.startsWith("/daai");
  const label = daai ? t("acc.daai_console") : t("acc.signin_btn");
  return (
    <a className={`btn btn-ghost btn-sm account-btn${daai ? "" : " is-signin"}`} href={href} aria-current={here ? "page" : undefined}>
      <Icon name={daai ? "layers" : "lock"} />
      <span className="account-btn-label">{label}</span>
    </a>
  );
}

/** The signed-in seeker's menu: opens under the name, closes on a choice, outside click, Escape or page change. */
function AccountMenu({ account, missing, here }) {
  const { t } = useI18n();
  const { path } = useHashPath();
  const [open, setOpen] = useState(false);
  const box = useRef(null);
  useEffect(() => { setOpen(false); }, [path]);
  useEffect(() => {
    if (!open) return undefined;
    const items = () => [...box.current.querySelectorAll("[role=menuitem]")];
    items()[0]?.focus();
    const away = (e) => { if (!box.current.contains(e.target)) setOpen(false); };
    const keys = (e) => {
      if (e.key === "Escape") { setOpen(false); box.current.querySelector(".account-btn").focus(); return; }
      if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return;
      e.preventDefault();
      const list = items(); const i = list.indexOf(document.activeElement);
      list[(i + (e.key === "ArrowDown" ? 1 : list.length - 1)) % list.length]?.focus();
    };
    document.addEventListener("mousedown", away);
    document.addEventListener("keydown", keys);
    return () => { document.removeEventListener("mousedown", away); document.removeEventListener("keydown", keys); };
  }, [open]);
  const signout = async () => { setOpen(false); await signOutSeeker(); toast(t("acc.signed_out")); };
  return (
    <div className="account-menu" ref={box}>
      <button type="button" className="btn btn-ghost btn-sm account-btn" aria-haspopup="menu" aria-expanded={open}
        aria-current={here ? "page" : undefined} aria-label={`${account.username}: ${t(missing ? "acc.complete_title" : "acc.mine")}`}
        onClick={() => setOpen(!open)}>
        <Icon name="users" />
        <span className="account-btn-label">{account.username}</span>
        {missing && <span className="account-dot" aria-hidden="true" />}
      </button>
      {open && (
        <div className="account-pop" role="menu" aria-label={t("acc.mine")}>
          <p className="account-pop-name">{account.username}</p>
          <a role="menuitem" href="#/account" onClick={() => setOpen(false)}><Icon name="users" />{t("acc.mine")}</a>
          <a role="menuitem" href="#/community?tab=mine" onClick={() => setOpen(false)}><Icon name="calendar" />{t("acc.menu_activities")}</a>
          <a role="menuitem" href="#/ask" onClick={() => setOpen(false)}><Icon name="chat" />{t("acc.menu_chats")}</a>
          <button type="button" role="menuitem" className="account-pop-out" onClick={signout}><Icon name="logout" />{t("acc.signout")}</button>
        </div>
      )}
    </div>
  );
}
