// About, Sources, Privacy, More and Not-found pages. Shared.
import { api, forgetSeeker } from "../core/api.js";
import { register, useI18n } from "../core/i18n.jsx";
import { Icon, Notice, errorText, toast } from "../core/ui.jsx";
import { loadAccount, useAccount, useDaaiSignedIn } from "../features/account/public.js";

register({
  ar: {
    "about.title": "عن سَبِيلي",
    "about.p1": "سَبِيلي تطبيق ويب يتيح لمن يثير الإسلام فضوله، وللمسلم الجديد، أن يسأل بلغته ويحصل على شرح واضح يستند إلى مصادر معتمدة مع إظهارها، وأن يتصل مباشرة بداعية متاح بلغته، ويتابع تعلّمه في مجموعات ولقاءات.",
    "about.ai_t": "مساعد بالذكاء الاصطناعي", "about.ai": "الإجابات يكتبها نموذج ذكاء اصطناعي (Gemma من Google عبر OpenRouter) مقيداً بالنصوص المسترجعة من الحزمة المعتمدة، وتُحذف أي جملة لا تستند إلى نص منها. ليس عالماً ولا مفتياً، ويقول «لم أجد» حين لا تكفي المصادر.",
    "about.how_t": "كيف تُبنى الإجابة", "about.how1": "تحليل السؤال: لغته ومستوى المحتوى (أ–د) وهل هو حالة شخصية.",
    "about.how2": "البحث في المصادر المعتمدة بالعربية والإنجليزية، ومطابقة أي آية منقولة أو مصوّرة بنص المصحف.",
    "about.how3": "كتابة الإجابة مع الإسناد لكل عبارة، وعرض الآيات والأحاديث من المرجع حرفياً لا من النموذج.",
    "about.how4": "التحقق بعد الكتابة: حذف أي نص قرآني يكتبه النموذج من ذاكرته، وإضافة تنبيه الفتوى عند الحالات الشخصية.",
    "about.calls_t": "الاتصال مستقل عن النموذج", "about.calls": "يمكن طلب داعية مباشرة دون سؤال المساعد، ويبقى الاتصال متاحاً إن تعطل النموذج.",
    "about.team_t": "الفريق", "about.m": "مهندس ذكاء اصطناعي: قراءة النص والمطابقة والاسترجاع والتقييم، والمجتمع.",
    "about.e": "مهندسة ذكاء اصطناعي: الاتصال بالداعية وملخص الإحالة.",
    "about.start": "هذه نسخة البداية الموثقة قبل أيام التحدي (4–6 أكتوبر 2026).",
    "src.title": "المصادر", "src.lead": "يجيب سَبِيلي من نصوص الحزمة العلمية المعتمدة في التحدي فقط، ويعرض المصدر مع كل إجابة.",
    "src.q": "نص المصحف (مجمع الملك فهد) والتفسير الميسر، عبر موسوعة القرآن الكريم QuranEnc (arabic_moyassar).",
    "src.qen": "ترجمة معاني القرآن إلى الإنجليزية، مركز رواد للترجمة، عبر QuranEnc (english_rwwad).",
    "src.h": "موسوعة الأحاديث النبوية HadeethEnc: أحاديث صحيحة مع درجتها وتخريجها وشرحها.",
    "src.t": "نماذج قاموس المصطلحات الأساسية من وثيقة «المرجعية والحزمة العلمية والبيانات» للتحدي.",
    "src.names": "أسماء السور من واجهة mp3quran.net العامة.",
    "src.icadb_note": "موسوعتا الأسئلة والأجوبة لغير المسلمين وللمسلمين، من قاعدة بيانات المحتوى الإسلامي (icadb) لجمعية خدمة المحتوى الإسلامي باللغات. الآيات داخل أجوبتهما تُعرض من نص المصحف.",
    "src.bayyinat_note": "كتاب «بينات: أسئلة وأجوبة عن الإسلام» (مركز أصول)، المرجع المعتمد في الحزمة للشبهات والأسئلة المتكررة. الآيات فيه تُعرض من نص المصحف.",
    "src.v": "قسم «مرئيات»: مقاطع موقع دار الإسلام (IslamHouse) عبر واجهته البرمجية الرسمية، تُعرض من موقعهم كما نُشرت مع رابط لكل مقطع.",
    "src.later": "مقترح للإضافة: قاموس الجمهرة، والدرر السنية.",
    "src.license": "تتيح الجمعية محتوى منصاتها مجاناً للأفراد والجهات عبر واجهات برمجية عامة، بحسب بيانها في الحزمة العلمية.",
    "priv.title": "الخصوصية", "priv.lead": "صممنا سَبِيلي ليعمل دون أن نعرف من أنت.",
    "priv.1": "الحساب اختياري: تبدأ برمز جلسة عشوائي في متصفحك، ولو أنشأت حساباً فهو اسم مستخدم وكلمة مرور، وبريد اختياري لاستعادته فقط، بلا جوال ولا اسم حقيقي. وعند إنشاء الحساب تختار جنسك وفئتك العمرية (لا تاريخ ميلادك) لنقترح عليك ما يناسبك، ولك أن تضيف لغتك ودولتك ومدينتك. لا يظهر شيء منها لأحد، وتغيّرها متى شئت، وتحذفها كلها بحذف الحساب.",
    "priv.2": "أسئلتك وإجاباتها تُحذف تلقائياً بعد 24 ساعة. وإن كنت داخل حسابك فتُحفظ فيه لتراها على أي جهاز، ومحادثات هذا المتصفح قبل دخولك تنتقل إليه، حتى تحذف أيّاً منها من صفحة اسأل، أو كلها من صفحة حسابي، أو تحذف الحساب.",
    "priv.3": "ملخص الإحالة ومحادثتك مع سَبِيلي لا يصلان إلى الداعية إلا بموافقتك الصريحة، ولكلٍّ منهما موافقة مستقلة. ولا يرى الداعية إلا المحادثة التي اخترتها، كما كانت لحظة موافقتك.",
    "priv.4": "المكالمات لا تُسجّل، ولا نطلب رقم هاتف. في المجموعات واللقاءات اسم مستعار فقط.",
    "priv.5": "لا نستنتج معتقدك أو أي صفة حساسة عنك، ولا نستخدم بياناتك لغير تقديم الخدمة.",
    "priv.6": "تُرسل الأسئلة إلى نموذج Gemma عبر OpenRouter لتوليد الإجابة، وإلى مزوّدين لا يحفظون الطلبات ولا يدرّبون عليها فقط.",
    "priv.7": "المقاطع المرئية وصورها تُحمَّل من خوادم دار الإسلام مباشرة، كأي زيارة لموقعهم. ولا يحفظ سَبِيلي ما تبحث عنه ولا ما تشاهده.",
    "priv.delete": "احذف بياناتي الآن", "priv.deleted": "حُذفت بياناتك من الخادم وبدأت جلسة جديدة.",
    "more.title": "المزيد", "more.lang": "اللغة", "more.theme": "المظهر", "more.light": "فاتح", "more.dark": "داكن", "more.auto": "تلقائي",
  },
  en: {
    "about.title": "About Sabeeli",
    "about.p1": "Sabeeli is a web app where anyone curious about Islam, and new Muslims, can ask in their own language and get a clear explanation grounded in approved sources that are shown alongside, call an available da'i who speaks their language, and keep learning in groups and meetups.",
    "about.ai_t": "An AI assistant", "about.ai": "Answers are written by an AI model (Gemma by Google, through OpenRouter), limited to passages retrieved from the approved package; any sentence not backed by one of them is removed. It is not a scholar or a mufti, and it says \"I couldn't find this\" when the sources aren't enough.",
    "about.how_t": "How an answer is built", "about.how1": "Analyse the question: its language, content level (A-D) and whether it's a personal case.",
    "about.how2": "Search the approved sources in Arabic and English, and match any quoted or photographed verse against the Mushaf.",
    "about.how3": "Write the answer with a source for each statement; verses and hadiths are shown from the reference, never from the model.",
    "about.how4": "Check after writing: remove any Quran text the model typed from memory, and add the fatwa notice for personal cases.",
    "about.calls_t": "Calls don't depend on the model", "about.calls": "You can ask for a da'i directly without asking the assistant, and calls keep working if the model is down.",
    "about.team_t": "Team", "about.m": "AI engineer: text reading, matching, retrieval and evaluation, and the community.",
    "about.e": "AI engineer: calls with a da'i and the referral summary.",
    "about.start": "This is the documented starting version, before the challenge days (4–6 October 2026).",
    "src.title": "Sources", "src.lead": "Sabeeli answers only from the challenge's approved scholarly package and shows the source with every answer.",
    "src.q": "The Mushaf text (King Fahd Complex) and At-Tafsir Al-Muyassar, via the Quran encyclopedia QuranEnc (arabic_moyassar).",
    "src.qen": "English translation of the meanings by the Rowwad Translation Center, via QuranEnc (english_rwwad).",
    "src.h": "The Encyclopedia of Translated Prophetic Hadiths (HadeethEnc): authentic hadiths with grade, attribution and explanation.",
    "src.t": "The sample glossary of core terms from the challenge's scholarly package.",
    "src.names": "Surah names from the public mp3quran.net API.",
    "src.icadb_note": "The Q&A encyclopedias for non-Muslims and for Muslims, from the Islamic Content Service Association's content database (icadb), in Arabic. Verses inside their answers are shown from the Mushaf text.",
    "src.bayyinat_note": "The book “Bayyinat: Questions and Answers about Islam” (Osoul Center), the package's reference for doubts and recurring questions, in Arabic. Verses in it are shown from the Mushaf text.",
    "src.v": "The Videos section: videos from IslamHouse through its official API, played from IslamHouse as published, each with a link to its page.",
    "src.later": "Proposed: the Jamhara dictionary and Dorar.",
    "src.license": "The association makes its platforms' content free for individuals and organisations through public APIs, per its statement in the package.",
    "priv.title": "Privacy", "priv.lead": "Sabeeli is designed to work without knowing who you are.",
    "priv.1": "An account is optional: you start with a random session token in your browser, and an account is a username and password, with an optional email used only to recover it. When you create one you pick your sex and an age band (never your birth date) so we can suggest what fits you, and you may add your language, country and city. Nobody else sees them, you can change them at any time, and deleting the account removes them all.",
    "priv.2": "Your questions and answers are deleted automatically after 24 hours. If you're signed in, they are saved to your account so you can see them on any device, and the chats this browser had before you signed in move there too. They stay until you delete one on the Ask page, all of them on My account, or the account itself.",
    "priv.3": "The referral summary and your chat with Sabeeli only reach a da'i with your explicit consent, given separately for each. The da'i sees only the chat you chose, as it was when you agreed.",
    "priv.4": "Calls aren't recorded and we never ask for a phone number. Groups and meetups use nicknames only.",
    "priv.5": "We don't infer your beliefs or any sensitive trait, and we use your data only to provide the service.",
    "priv.6": "Questions are sent to the Gemma model through OpenRouter to write answers, only to providers that neither store requests nor train on them.",
    "priv.7": "Videos and their thumbnails load straight from IslamHouse's servers, like any visit to their site. Sabeeli doesn't save what you search for or what you watch.",
    "priv.delete": "Delete my data now", "priv.deleted": "Your data was deleted from the server and a new session started.",
    "more.title": "More", "more.lang": "Language", "more.theme": "Theme", "more.light": "Light", "more.dark": "Dark", "more.auto": "Auto",
  },
});

export function About() {
  const { t, fmtNum } = useI18n();
  return (
    <>
      <div className="page-head"><h1>{t("about.title")}</h1><p>{t("about.p1")}</p></div>
      <div className="grid grid-2">
        <div className="card stack"><h3><Icon name="sparkle" /> {t("about.ai_t")}</h3><p className="muted">{t("about.ai")}</p></div>
        <div className="card stack"><h3>{t("about.calls_t")}</h3><p className="muted">{t("about.calls")}</p></div>
      </div>
      <section className="section card stack">
        <h3>{t("about.how_t")}</h3>
        <ol className="steps">
          {["how1", "how2", "how3", "how4"].map((k, i) => <li className="step" key={k}><span className="step-num">{fmtNum(i + 1)}</span><p>{t(`about.${k}`)}</p></li>)}
        </ol>
      </section>
      <section className="section card stack">
        <h3>{t("about.team_t")}</h3>
        <div className="grid grid-2">
          <div><strong>Mushari Alothman</strong><p className="muted small">{t("about.m")}</p></div>
          <div><strong>Eman Saheli</strong><p className="muted small">{t("about.e")}</p></div>
        </div>
      </section>
      <p className="faint">{t("about.start")}</p>
    </>
  );
}

const SOURCES = [
  ["src.q", "https://quranenc.com/ar/browse/arabic_moyassar"], ["src.qen", "https://quranenc.com/en/browse/english_rwwad"],
  ["src.h", "https://hadeethenc.com"], ["src.icadb_note", "https://islamenc.com/ar/enc-cards/110"],
  ["src.bayyinat_note", "https://dawa.center/file/7937"], ["src.t", ""], ["src.names", "https://www.mp3quran.net/api"],
  ["src.v", "https://islamhouse.com/"],
];

export function Sources() {
  const { t } = useI18n();
  return (
    <>
      <div className="page-head"><h1>{t("src.title")}</h1><p>{t("src.lead")}</p></div>
      <div className="stack">
        {SOURCES.map(([k, url]) => (
          <div className="card row spread" key={k}>
            <p style={{ margin: 0, flex: 1 }}>{t(k)}</p>
            {url && <a className="btn btn-sm" href={url} target="_blank" rel="noopener noreferrer" aria-label={t("src.open")}><Icon name="external" /></a>}
          </div>
        ))}
      </div>
      <div className="section"><Notice icon="info">{t("src.license")}</Notice></div>
      <p className="faint">{t("src.later")}</p>
    </>
  );
}

export function Privacy() {
  const { t } = useI18n();
  const wipe = async () => {
    try {
      await api.del("/api/me");
    } catch (err) {
      // Only "no such session" means there is nothing left to delete; anything else (offline, a server
      // error) must not be reported as deleted.
      if (err.status !== 401 && err.status !== 404) { toast(errorText(err, t), "error"); return; }
    }
    forgetSeeker();
    try { sessionStorage.clear(); } catch { /* ignore */ }
    loadAccount();   // the account went with the data: the top bar must stop showing its name
    toast(t("priv.deleted"));
  };
  return (
    <>
      <div className="page-head"><h1>{t("priv.title")}</h1><p>{t("priv.lead")}</p></div>
      <ul className="priv-list">
        {["priv.1", "priv.2", "priv.3", "priv.4", "priv.5", "priv.6", "priv.7"].map((k) => <li key={k}><Icon name="shield" size={22} /><span>{t(k)}</span></li>)}
      </ul>
      <div className="section"><button type="button" className="btn btn-danger" onClick={wipe}><Icon name="trash" />{t("priv.delete")}</button></div>
    </>
  );
}

export function More({ theme, setTheme }) {
  const { t, lang, setLang } = useI18n();
  const { account, loaded } = useAccount();
  const daai = useDaaiSignedIn();
  const link = (href, icon, key) => <a className="card card-link row more-link" href={href}><Icon name={icon} size={22} /><span>{t(key)}</span><Icon name="arrow" className="icon-go more-chev" size={18} /></a>;
  return (
    <>
      <div className="page-head"><h1>{t("more.title")}</h1></div>
      <div className="stack">
        {/* Signing in is offered only to someone who isn't signed in; once signed in, the top bar holds the account. */}
        {loaded && !account && !daai && link("#/account", "lock", "acc.signin_btn")}
        {link("#/about", "info", "nav.about")}
        {link("#/sources", "book", "nav.sources")}
        {link("#/privacy", "shield", "nav.privacy")}
        {link("#/daai", "users", daai ? "nav.daai" : "footer.daai")}
        <div className="card stack">
          <strong>{t("more.lang")}</strong>
          <div className="tabs tabs-fit">
            {[["ar", "العربية"], ["en", "English"]].map(([l, label]) => (
              <button key={l} type="button" aria-selected={lang === l} onClick={() => setLang(l)}>{label}</button>
            ))}
          </div>
          <strong>{t("more.theme")}</strong>
          <div className="tabs tabs-fit">
            {[["auto", "more.auto"], ["light", "more.light"], ["dark", "more.dark"]].map(([v, k]) => (
              <button key={v} type="button" aria-selected={theme === v} onClick={() => setTheme(v)}>{t(k)}</button>
            ))}
          </div>
        </div>
      </div>
    </>
  );
}

export function NotFound() {
  const { t } = useI18n();
  return (
    <div className="empty not-found">
      <Icon name="search" size={46} />
      <p className="nf-code" aria-hidden="true">404</p>
      <h1>{t("nf.title")}</h1>
      <p>{t("nf.lead")}</p>
      <div className="row nf-actions">
        <a className="btn btn-primary" href="#/"><Icon name="home" />{t("nav.home")}</a>
        <a className="btn" href="#/ask"><Icon name="ask" />{t("nav.ask")}</a>
      </div>
    </div>
  );
}
