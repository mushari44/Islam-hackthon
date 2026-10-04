// Top bar entry: "Sign in" when signed out, the username when signed in. Owner: Eman.
// It also asks an older account that has no sex or age band yet to pick them, once per visit.
import "./strings.js";
import { useEffect } from "react";
import { useI18n } from "../../core/i18n.jsx";
import { Icon, openSheet } from "../../core/ui.jsx";
import { CompleteAbout, needsAbout } from "./fields.jsx";
import { useAccount } from "./store.js";

let asked = false;   // once per page load: closing the question doesn't bring it straight back

export function AccountButton() {
  const { t } = useI18n();
  const { account } = useAccount();
  const missing = needsAbout(account);
  useEffect(() => {
    if (!missing || asked || window.location.hash.startsWith("#/account")) return undefined;   // the account page asks itself
    asked = true;
    const timer = setTimeout(() => openSheet({ title: t("acc.complete_title"), render: (close) => <CompleteAbout account={account} close={close} /> }));
    return () => clearTimeout(timer);
  }, [missing]); // eslint-disable-line react-hooks/exhaustive-deps
  return (
    <a className="btn btn-ghost btn-sm account-btn" href="#/account" aria-label={account ? (missing ? `${t("acc.mine")}: ${t("acc.complete_title")}` : t("acc.mine")) : t("acc.signin")}>
      <Icon name={account ? "users" : "lock"} />
      <span className="account-btn-label">{account ? account.username : t("acc.signin")}</span>
      {missing && <span className="account-dot" aria-hidden="true" />}
    </a>
  );
}
