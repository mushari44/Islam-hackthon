// Strings, language and direction. Shared core.
// Each feature registers its own strings (register({ar: {...}, en: {...}})) so nobody edits another feature's text.
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

const dict = { ar: {}, en: {} };

export function register(strings) {
  for (const l of ["ar", "en"]) Object.assign(dict[l], strings[l] || {});
}

export function translate(lang, key, vars = {}) {
  const s = dict[lang][key] ?? dict.en[key] ?? key;
  return s.replace(/\{(\w+)\}/g, (_, k) => (vars[k] ?? ""));
}

const locale = (lang) => (lang === "ar" ? "ar-SA-u-nu-arab-ca-gregory" : "en-GB");

export const LANG_NAMES = {
  ar: { ar: "العربية", en: "Arabic" }, en: { ar: "الإنجليزية", en: "English" }, fr: { ar: "الفرنسية", en: "French" },
  ur: { ar: "الأردية", en: "Urdu" }, id: { ar: "الإندونيسية", en: "Indonesian" }, tr: { ar: "التركية", en: "Turkish" },
  es: { ar: "الإسبانية", en: "Spanish" }, de: { ar: "الألمانية", en: "German" }, bn: { ar: "البنغالية", en: "Bengali" },
  ru: { ar: "الروسية", en: "Russian" }, zh: { ar: "الصينية", en: "Chinese" }, sw: { ar: "السواحلية", en: "Swahili" },
};

function initialLang() {
  try {
    const saved = localStorage.getItem("sabeeli.lang");
    if (saved) return saved === "en" ? "en" : "ar";
  } catch { /* private mode */ }
  return (navigator.language || "ar").toLowerCase().startsWith("en") ? "en" : "ar";
}

const LangContext = createContext(null);

export function LangProvider({ children }) {
  const [lang, setLangState] = useState(initialLang);
  useEffect(() => {
    document.documentElement.lang = lang;
    document.documentElement.dir = lang === "ar" ? "rtl" : "ltr";
    try { localStorage.setItem("sabeeli.lang", lang); } catch { /* ignore */ }
  }, [lang]);
  const setLang = useCallback((l) => setLangState(l === "en" ? "en" : "ar"), []);
  const value = useMemo(() => {
    const loc = locale(lang);
    return {
      lang,
      setLang,
      t: (key, vars) => translate(lang, key, vars),
      // Counted text: "key.one", "key.two", "key.few", "key.many" (CLDR plural forms) when this language has them,
      // else "key". {n} is the formatted number. Arabic needs all of them; English needs only "key.one".
      tn: (key, n, vars = {}) => {
        const form = `${key}.${new Intl.PluralRules(lang).select(n)}`;
        return translate(lang, dict[lang][form] !== undefined ? form : key, { ...vars, n: new Intl.NumberFormat(loc).format(n) });
      },
      fmtNum: (n) => new Intl.NumberFormat(loc).format(n),
      fmtDate: (iso, opts = { weekday: "long", day: "numeric", month: "long" }) => new Intl.DateTimeFormat(loc, opts).format(new Date(iso)),
      fmtTime: (iso) => new Intl.DateTimeFormat(loc, { hour: "numeric", minute: "2-digit" }).format(new Date(iso)),
      fmtAgo: (iso) => {
        const sec = Math.max(1, Math.round((Date.now() - new Date(iso).getTime()) / 1000));
        const rtf = new Intl.RelativeTimeFormat(loc, { numeric: "auto" });
        if (sec < 60) return rtf.format(-sec, "second");
        if (sec < 3600) return rtf.format(-Math.round(sec / 60), "minute");
        if (sec < 86400) return rtf.format(-Math.round(sec / 3600), "hour");
        return rtf.format(-Math.round(sec / 86400), "day");
      },
      langName: (code) => (LANG_NAMES[code] ? LANG_NAMES[code][lang] : code),
    };
  }, [lang, setLang]);
  return <LangContext.Provider value={value}>{children}</LangContext.Provider>;
}

/** const { t, lang, fmtNum, ... } = useI18n(); */
export function useI18n() {
  return useContext(LangContext);
}

register({
  ar: {
    "app.name": "سَبِيلي",
    "nav.home": "الرئيسية", "nav.ask": "اسأل", "nav.talk": "تحدّث", "nav.community": "المجتمع", "nav.more": "المزيد",
    "nav.daai": "لوحة الداعية", "nav.about": "عن سَبِيلي", "nav.sources": "المصادر", "nav.privacy": "الخصوصية",
    "common.close": "إغلاق", "common.cancel": "إلغاء", "common.save": "حفظ", "common.send": "إرسال", "common.back": "رجوع",
    "common.loading": "جارٍ التحميل…", "common.retry": "إعادة المحاولة", "common.error": "حدث خطأ، حاول مرة أخرى.",
    "common.offline": "تعذر الاتصال بالخادم.", "common.yes": "نعم", "common.no": "لا",
    "common.lang_toggle": "English", "common.lang_short": "EN", "common.theme": "تبديل المظهر", "common.skip": "انتقل إلى المحتوى",
    "common.optional": "اختياري", "common.continue": "متابعة", "common.done": "تم",
    "footer.ai": "سَبِيلي مساعد بالذكاء الاصطناعي، وليس عالماً ولا مفتياً. المصادر تظهر مع كل إجابة.",
    "footer.challenge": "مشروع في تحدي الذكاء الاصطناعي في خدمة المحتوى الإسلامي 2026",
    "footer.links": "روابط الموقع", "footer.daai": "دخول الدعاة", "nav.main_label": "القائمة الرئيسية",
    "nf.title": "الصفحة غير موجودة", "nf.lead": "ربما تغيّر الرابط أو كُتب خطأ. ارجع إلى الرئيسية أو اسأل سؤالك مباشرة.",
    "unit.s": "{n} ث", "unit.m": "{n} د",
    "err.full": "اكتمل العدد.", "err.nickname taken in this group": "هذا الاسم مستخدم في المجموعة، اختر غيره.",
    "err.choose another nickname": "اختر اسماً مستعاراً آخر.", "err.please accept the group rules": "يلزم الموافقة على قواعد المجموعة.",
    "err.please confirm the audience of this meetup": "يرجى تأكيد أن الفعالية تناسبك.", "err.unsupported image type": "نوع الصورة غير مدعوم. استخدم JPG أو PNG أو WEBP.",
    "err.image too large (max 5 MB)": "حجم الصورة أكبر من 5 ميجابايت.", "err.join the group first": "انضم إلى المجموعة أولاً.",
    "err.meetups must be at a public venue": "يجب أن تكون الفعالية في مكان عام.", "err.already taken or no longer waiting": "قبل داعية آخر هذا الطلب.",
    "err.empty question": "اكتب سؤالك أولاً.", "err.not found": "غير موجود.", "err.session": "تعذر بدء الجلسة، حاول مرة أخرى.",
  },
  en: {
    "app.name": "Sabeeli",
    "nav.home": "Home", "nav.ask": "Ask", "nav.talk": "Talk", "nav.community": "Community", "nav.more": "More",
    "nav.daai": "Da'i console", "nav.about": "About", "nav.sources": "Sources", "nav.privacy": "Privacy",
    "common.close": "Close", "common.cancel": "Cancel", "common.save": "Save", "common.send": "Send", "common.back": "Back",
    "common.loading": "Loading…", "common.retry": "Try again", "common.error": "Something went wrong. Please try again.",
    "common.offline": "Couldn't reach the server.", "common.yes": "Yes", "common.no": "No",
    "common.lang_toggle": "العربية", "common.lang_short": "ع", "common.theme": "Toggle theme", "common.skip": "Skip to content",
    "common.optional": "optional", "common.continue": "Continue", "common.done": "Done",
    "footer.ai": "Sabeeli is an AI assistant, not a scholar or a mufti. Sources are shown with every answer.",
    "footer.challenge": "A project in the AI Challenge Serving Islamic Content 2026",
    "footer.links": "Site links", "footer.daai": "Da'i sign-in", "nav.main_label": "Main menu",
    "nf.title": "Page not found", "nf.lead": "The link may have changed or been mistyped. Go back home or ask your question directly.",
    "unit.s": "{n}s", "unit.m": "{n} min",
    "err.full": "This event is full.", "err.nickname taken in this group": "That nickname is taken in this group; choose another.",
    "err.choose another nickname": "Please choose another nickname.", "err.please accept the group rules": "Please accept the group rules.",
    "err.please confirm the audience of this meetup": "Please confirm this event is for you.", "err.unsupported image type": "Unsupported image type. Use JPG, PNG or WEBP.",
    "err.image too large (max 5 MB)": "The photo is larger than 5 MB.", "err.join the group first": "Join the group first.",
    "err.meetups must be at a public venue": "Events must be at a public venue.", "err.already taken or no longer waiting": "Another da'i took this request.",
    "err.empty question": "Type your question first.", "err.not found": "Not found.", "err.session": "Couldn't start a session; please try again.",
  },
});
