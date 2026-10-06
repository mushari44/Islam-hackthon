// "My activities": the meetups this seeker booked (coming up first) and the groups they are in. Owner: Mushari.
import { useI18n } from "../../core/i18n.jsx";
import { Icon, Notice, errorText } from "../../core/ui.jsx";
import { GroupCard, MeetupCard } from "./cards.jsx";
import { useNow } from "./shared.jsx";

export default function MyActivities({ data, reload, account, browse }) {
  const { t, fmtNum } = useI18n();
  const now = useNow();
  if (!data) return <div className="skeleton" style={{ height: 120 }} />;
  if (data.error) {
    return (
      <div className="empty">
        <p>{errorText(data.error, t)}</p>
        <button type="button" className="btn btn-sm" onClick={reload}>{t("common.retry")}</button>
      </div>
    );
  }
  const over = (m) => m.status === "cancelled" || new Date(m.starts_at).getTime() + m.duration_min * 60000 <= now;
  const upcoming = data.meetups.filter((m) => !over(m));
  const past = data.meetups.filter(over).reverse();
  return (
    <div className="stack mine">
      {!account && <Notice icon="lock">{t("com.mine_device")} <a href="#/account?next=%2Fcommunity%3Ftab%3Dmine">{t("com.mine_signin")}</a></Notice>}
      <section className="stack">
        <h2 className="mine-h"><Icon name="calendar" />{t("com.mine_upcoming")}</h2>
        {upcoming.length
          ? <div className="stack">{upcoming.map((m) => <MeetupCard key={m.id} m={m} reload={reload} account={account} />)}</div>
          : (
            <div className="card mine-empty">
              <p className="muted">{t("com.mine_none")}</p>
              <button type="button" className="btn btn-primary btn-sm" onClick={() => browse("meetups")}><Icon name="search" />{t("com.browse_events")}</button>
            </div>
          )}
      </section>
      <section className="stack">
        <h2 className="mine-h"><Icon name="users" />{t("com.mine_groups")}</h2>
        {data.groups.length
          ? <div className="grid grid-2">{data.groups.map((g) => <GroupCard key={g.id} g={g} />)}</div>
          : (
            <div className="card mine-empty">
              <p className="muted">{t("com.mine_no_groups")}</p>
              <button type="button" className="btn btn-sm" onClick={() => browse("groups")}><Icon name="search" />{t("com.browse_groups")}</button>
            </div>
          )}
      </section>
      {past.length > 0 && (
        <details className="mine-past">
          <summary>{t("com.mine_past", { n: fmtNum(past.length) })}</summary>
          <div className="stack">{past.map((m) => <MeetupCard key={m.id} m={m} reload={reload} account={account} />)}</div>
        </details>
      )}
    </div>
  );
}
