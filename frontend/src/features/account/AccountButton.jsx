// Top bar entry: "Sign in" when signed out, the username when signed in. Owner: Eman.
import "./strings.js";
import { useI18n } from "../../core/i18n.jsx";
import { Icon } from "../../core/ui.jsx";
import { useAccount } from "./store.js";

export function AccountButton() {
  const { t } = useI18n();
  const { account } = useAccount();
  return (
    <a className="btn btn-ghost btn-sm account-btn" href="#/account" aria-label={account ? t("acc.mine") : t("acc.signin")}>
      <Icon name={account ? "users" : "lock"} />
      <span className="account-btn-label">{account ? account.username : t("acc.signin")}</span>
    </a>
  );
}
