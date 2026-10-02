// What other features may use from Calls. Owner: Eman.
// RAG's "Talk to a da'i about this" button calls startReferral({lang, t}).
import { openSheet } from "../../core/ui.jsx";
import ReferralSheet from "./ReferralSheet.jsx";

export function startReferral({ lang, t }) {
  return openSheet({ title: t("ref.title"), render: (close) => <ReferralSheet lang={lang} close={close} /> });
}
