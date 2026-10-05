// Top bar entry, last in the bar: "Sign in" when signed out, the username for a seeker, "Da'i console" for a da'i. Owner: Eman.
// It also asks an older account that has no sex or age band yet to pick them, once per visit.
import "./strings.js";
import { useEffect } from "react";
import { useI18n } from "../../core/i18n.jsx";
import { useHashPath } from "../../core/router.jsx";
import { Icon, openSheet } from "../../core/ui.jsx";
import { CompleteAbout, needsAbout } from "./fields.jsx";
import { useAccount, useDaaiSignedIn } from "./store.js";

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
  // Signed out, the button opens the sign-in card, which /daai shows too (with "da'i" picked).
  const href = account ? "#/account" : daai ? "#/daai" : "#/account";
  const here = account ? path.startsWith("/account") : daai ? path.startsWith("/daai") : path.startsWith("/account") || path.startsWith("/daai");
  const label = account ? account.username : daai ? t("acc.daai_console") : t("acc.signin_btn");
  return (
    <a className={`btn btn-ghost btn-sm account-btn${account || daai ? "" : " is-signin"}`} href={href}
      aria-current={here ? "page" : undefined} aria-label={account ? (missing ? `${t("acc.mine")}: ${t("acc.complete_title")}` : t("acc.mine")) : label}>
      <Icon name={account ? "users" : daai ? "layers" : "lock"} />
      <span className="account-btn-label">{label}</span>
      {missing && <span className="account-dot" aria-hidden="true" />}
    </a>
  );
}
