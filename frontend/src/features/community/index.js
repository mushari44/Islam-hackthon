// What the shared shell may import from Community. Owner: Mushari.
import { DaaiGroupsPanel, DaaiMeetupsPanel } from "./DaaiPanels.jsx";

export { default as CommunityPage } from "./CommunityPage.jsx";
export { default as GroupPage } from "./GroupPage.jsx";

export const communityTabs = [
  { key: "groups", labelKey: "dg.tab", component: DaaiGroupsPanel },
  { key: "meetups", labelKey: "dm.tab", component: DaaiMeetupsPanel },
];
