export const LOCALES = ["bn", "en"] as const;
export type Locale = (typeof LOCALES)[number];

export const ROUTES = ["", "outlets", "methodology", "data"] as const;
export type Route = (typeof ROUTES)[number];

const en = {
  "site.name": "Takedown Watch",
  "site.tagline": "A record of Bangladesh's online news: what was published, kept, and changed.",
  "site.org": "A project of Activate Rights",
  "site.successor": "Successor to Shutdown Watch",
  "skip": "Skip to content",
  "nav.label": "Main",
  "nav.": "Overview",
  "nav.outlets": "Outlets",
  "nav.methodology": "Methodology",
  "nav.data": "Data",
  "lang.switch": "বাংলা",
  "lang.switchLabel": "Read this page in Bangla",

  "overview.title": "Capture coverage",
  "overview.lede": "Operational figures on capturing every article the monitored outlets publish, never findings about any outlet.",
  "overview.calendar": "Captures by day",
  "overview.calendarNote": "Each mark is one day, Bangladesh time. The larger the mark, the more pages were captured that day.",
  "overview.began": "Monitoring began",
  "overview.notBegun": "Monitoring has not produced captures yet.",
  "overview.legend.captures": "Pages captured",
  "overview.legend.zero": "Monitored, nothing captured",
  "overview.legend.before": "Before monitoring began",
  "overview.legend.today": "Latest day in the dataset",
  "overview.calendarAlt": "Calendar of daily captures",
  "overview.totals": "Totals",
  "overview.log": "Daily log",
  "overview.log.date": "Date",
  "overview.log.snapshots": "Pages captured",
  "overview.log.firstSeen": "Articles first seen",
  "overview.groups": "By language and outlet group",
  "overview.groupsNote":
    "Figures are only ever published for a group of outlets. A group with fewer than {min} outlets contributing captures is withheld, because a figure for one or two outlets would be a figure about them. A group is also withheld when subtracting its figures from another group's would single out such a small set.",

  "t.outletsMonitored": "Outlets monitored",
  "t.withSources": "With a working article source",
  "t.contributing": "Contributing captures",
  "t.discovered": "Articles discovered",
  "t.captured": "Articles captured",
  "t.snapshots": "Pages captured",
  "t.archived": "Independently archived",
  "t.archiveRate": "Archive rate",
  "t.archiveNone": "No submission to the Internet Archive has succeeded yet.",
  "overview.legend.scale": "Pages captured in a day",
  "t.captureRate": "Capture success",
  "t.health": "Extraction",
  "t.lastCapture": "Last capture",
  "t.lastListing": "Last check of feeds",
  "t.group": "Group",
  "t.monitored": "Monitored",
  "t.contributingShort": "Contributing",

  "withheld": "Withheld",
  "withheld.reason": "fewer than {min} outlets contributing",
  "withheld.complementary": "so that other figures cannot be subtracted to single out an outlet",
  "none": "None yet",

  "group.all": "All outlets",
  "group.language": "Language",
  "group.tier": "Outlet group",
  "lang.bn": "Bangla",
  "lang.en": "English",
  "tier.bangla_mass": "Bangla mass-circulation",
  "tier.bangla_other": "Bangla, other alignments",
  "tier.english": "English-language",
  "tier.online_native": "Online-native",
  "tier.state_wire": "State news agency",
  "tier.independent": "Independent",

  "health.ok": "Healthy",
  "health.degraded": "Degraded",
  "health.failing": "Failing",
  "health.no_data": "No data",
  "health.explain":
    "Extraction health compares each captured page's text length with its outlet's recent median. Many unusually short pages usually mean an outlet changed its page design and our extractor needs updating. Video and photo pages are short by nature and count here too.",

  "outlets.title": "Outlets monitored",
  "outlets.lede":
    "The cohort spans Bangla and English, mass-circulation and online-native, state and independent outlets. The spread is a methodological requirement: a monitor that watched only one kind of outlet would produce findings about that kind of outlet.",
  "outlets.policy":
    "No figure on this site is published for an individual outlet. Outlets are named here so it is clear what is monitored; everything measured is published only for groups.",
  "outlets.site": "Website",
  "outlets.count": "{n} outlets",
  "outlets.countOne": "1 outlet",
  "outlets.health": "Extraction health by group",

  "method.title": "Methodology",
  "method.state": "Current state of the system",
  "method.versions": "Versions in this dataset",
  "method.pipeline": "Pipeline",
  "method.extractor": "Extractor",
  "method.normaliser": "Text normaliser",
  "method.window": "Capture window",
  "method.hours": "{n} hours",
  "method.vantage": "Vantage points",

  "data.title": "Open data",
  "data.lede":
    "Everything on this site is built from these files, and nothing else. They are the dataset: download them, check the figures, build on them.",
  "data.file": "File",
  "data.contents": "Contents",
  "data.meta": "Versions, capture window, timestamps of the latest run.",
  "data.coverage": "Totals for all outlets, each language and each outlet group, with withheld groups marked.",
  "data.outlets": "The monitored outlets: name, language, group, website. No figures.",
  "data.extraction-health": "Extraction health by group, with the thresholds used.",
  "data.capture-volume": "Pages captured and articles first seen, per day, Bangladesh time.",
  "data.schema": "Schema version",
  "data.generated": "Generated",
  "data.licence": "Licence",
  "data.licenceText": "The licence for the dataset and this site's text has not been decided yet. Until it is, no licence is granted by publication here.",
  "data.contact": "Contact",
  "data.contactText": "Takedown Watch is run by Activate Rights.",
  "data.newsrooms": "For newsrooms",
  "data.newsroomsText":
    "Our crawler identifies itself as TakedownWatch in its User-Agent, with a link to activaterights.org. It requests at most one page every two seconds from any site, follows robots.txt, and does not attempt to bypass access controls such as Cloudflare challenges.",
  "data.rehost": "Mirroring this site",
  "data.rehostText":
    "The site is plain static files. Copy the built folder to any web server or open it from disk; set SITE_BASE when serving it from a sub-path.",

  "footer.dataset": "Dataset generated",
  "footer.schema": "schema",
} as const;

type Key = keyof typeof en;

const bn: Record<Key, string> = {
  "site.name": "টেকডাউন ওয়াচ",
  "site.tagline": "বাংলাদেশের অনলাইন সংবাদের নথি: কী প্রকাশিত হলো, কী রইল, কী বদলাল।",
  "site.org": "অ্যাক্টিভেট রাইটসের একটি প্রকল্প",
  "site.successor": "শাটডাউন ওয়াচের উত্তরসূরি",
  "skip": "মূল অংশে যান",
  "nav.label": "প্রধান",
  "nav.": "সারসংক্ষেপ",
  "nav.outlets": "সংবাদমাধ্যম",
  "nav.methodology": "পদ্ধতি",
  "nav.data": "ডেটা",
  "lang.switch": "English",
  "lang.switchLabel": "Read this page in English",

  "overview.title": "সংরক্ষণের পরিধি",
  "overview.lede": "পর্যবেক্ষণাধীন সংবাদমাধ্যমের প্রকাশিত প্রতিটি নিবন্ধ সংরক্ষণের কার্যকরী হিসাব; কোনো সংবাদমাধ্যম সম্পর্কে কোনো সিদ্ধান্ত নয়।",
  "overview.calendar": "দিনভিত্তিক সংরক্ষণ",
  "overview.calendarNote": "প্রতিটি চিহ্ন বাংলাদেশ সময় অনুযায়ী একটি দিন। চিহ্ন যত বড়, সেদিন তত বেশি পাতা সংরক্ষিত হয়েছে।",
  "overview.began": "পর্যবেক্ষণ শুরু",
  "overview.notBegun": "পর্যবেক্ষণ থেকে এখনো কোনো পাতা সংরক্ষিত হয়নি।",
  "overview.legend.captures": "সংরক্ষিত পাতা",
  "overview.legend.zero": "পর্যবেক্ষণ চলেছে, কিছু সংরক্ষিত হয়নি",
  "overview.legend.before": "পর্যবেক্ষণ শুরুর আগে",
  "overview.legend.today": "ডেটাসেটের সর্বশেষ দিন",
  "overview.calendarAlt": "দিনভিত্তিক সংরক্ষণের ক্যালেন্ডার",
  "overview.totals": "মোট হিসাব",
  "overview.log": "দৈনিক খতিয়ান",
  "overview.log.date": "তারিখ",
  "overview.log.snapshots": "সংরক্ষিত পাতা",
  "overview.log.firstSeen": "প্রথম দেখা নিবন্ধ",
  "overview.groups": "ভাষা ও সংবাদমাধ্যম-গোষ্ঠী অনুযায়ী",
  "overview.groupsNote":
    "সংখ্যা শুধু একাধিক সংবাদমাধ্যমের গোষ্ঠী হিসেবে প্রকাশ করা হয়। যে গোষ্ঠীতে {min}টির কম সংবাদমাধ্যম থেকে পাতা সংরক্ষিত হয়েছে, সেটির সংখ্যা প্রকাশ করা হয় না, কারণ এক বা দুটি সংবাদমাধ্যমের সংখ্যা মানে কার্যত সেগুলোরই সংখ্যা। কোনো গোষ্ঠীর সংখ্যা অন্য গোষ্ঠীর সংখ্যা থেকে বিয়োগ করলে যদি এমন ছোট একটি দল আলাদা হয়ে যায়, সেই গোষ্ঠীর সংখ্যাও প্রকাশ করা হয় না।",

  "t.outletsMonitored": "পর্যবেক্ষণাধীন সংবাদমাধ্যম",
  "t.withSources": "নিবন্ধের সচল উৎস আছে",
  "t.contributing": "পাতা সংরক্ষিত হচ্ছে",
  "t.discovered": "খুঁজে পাওয়া নিবন্ধ",
  "t.captured": "সংরক্ষিত নিবন্ধ",
  "t.snapshots": "সংরক্ষিত পাতা",
  "t.archived": "স্বতন্ত্রভাবে আর্কাইভকৃত",
  "t.archiveRate": "আর্কাইভের হার",
  "t.archiveNone": "ইন্টারনেট আর্কাইভে এখনো কোনো জমাদান সফল হয়নি।",
  "overview.legend.scale": "এক দিনে সংরক্ষিত পাতা",
  "t.captureRate": "সংরক্ষণে সাফল্য",
  "t.health": "পাঠ্য নিষ্কাশন",
  "t.lastCapture": "সর্বশেষ সংরক্ষণ",
  "t.lastListing": "ফিডের সর্বশেষ যাচাই",
  "t.group": "গোষ্ঠী",
  "t.monitored": "পর্যবেক্ষণাধীন",
  "t.contributingShort": "সংরক্ষিত হচ্ছে",

  "withheld": "প্রকাশ করা হয়নি",
  "withheld.reason": "{min}টির কম সংবাদমাধ্যম",
  "withheld.complementary": "অন্য সংখ্যা বিয়োগ করে কোনো একক সংবাদমাধ্যম যাতে চিহ্নিত করা না যায়",
  "none": "এখনো নেই",

  "group.all": "সব সংবাদমাধ্যম",
  "group.language": "ভাষা",
  "group.tier": "সংবাদমাধ্যম-গোষ্ঠী",
  "lang.bn": "বাংলা",
  "lang.en": "ইংরেজি",
  "tier.bangla_mass": "বহুল প্রচারিত বাংলা",
  "tier.bangla_other": "বাংলা, ভিন্ন ধারার",
  "tier.english": "ইংরেজি ভাষার",
  "tier.online_native": "অনলাইনভিত্তিক",
  "tier.state_wire": "রাষ্ট্রীয় সংবাদ সংস্থা",
  "tier.independent": "স্বাধীন",

  "health.ok": "সুস্থ",
  "health.degraded": "দুর্বল",
  "health.failing": "ব্যর্থ",
  "health.no_data": "তথ্য নেই",
  "health.explain":
    "প্রতিটি সংরক্ষিত পাতার পাঠ্যের দৈর্ঘ্য সংশ্লিষ্ট সংবাদমাধ্যমের সাম্প্রতিক মধ্যমার সঙ্গে তুলনা করা হয়। অস্বাভাবিক ছোট পাতা বেশি হলে সাধারণত বোঝায় সংবাদমাধ্যমটি পাতার নকশা বদলেছে এবং আমাদের নিষ্কাশন-পদ্ধতি হালনাগাদ করা দরকার। ভিডিও ও ছবির পাতা স্বভাবতই ছোট, সেগুলোও এখানে গণ্য হয়।",

  "outlets.title": "পর্যবেক্ষণাধীন সংবাদমাধ্যম",
  "outlets.lede":
    "এই তালিকায় আছে বাংলা ও ইংরেজি, বহুল প্রচারিত ও অনলাইনভিত্তিক, রাষ্ট্রীয় ও স্বাধীন সংবাদমাধ্যম। এই বৈচিত্র্য পদ্ধতিগত প্রয়োজন: শুধু এক ধরনের সংবাদমাধ্যম পর্যবেক্ষণ করলে যা পাওয়া যায় তা কেবল সেই ধরনটির সম্পর্কেই বলে।",
  "outlets.policy":
    "এই সাইটে কোনো একক সংবাদমাধ্যমের কোনো সংখ্যা প্রকাশ করা হয় না। কী পর্যবেক্ষণ করা হচ্ছে তা স্পষ্ট রাখতে এখানে নামগুলো দেওয়া হলো; যা কিছু মাপা হয়, তা শুধু গোষ্ঠী হিসেবে প্রকাশিত হয়।",
  "outlets.site": "ওয়েবসাইট",
  "outlets.count": "{n}টি সংবাদমাধ্যম",
  "outlets.countOne": "১টি সংবাদমাধ্যম",
  "outlets.health": "গোষ্ঠী অনুযায়ী পাঠ্য নিষ্কাশনের অবস্থা",

  "method.title": "পদ্ধতি",
  "method.state": "ব্যবস্থার বর্তমান অবস্থা",
  "method.versions": "এই ডেটাসেটের সংস্করণ",
  "method.pipeline": "পাইপলাইন",
  "method.extractor": "নিষ্কাশক",
  "method.normaliser": "পাঠ্য প্রমিতকারক",
  "method.window": "সংরক্ষণের সময়সীমা",
  "method.hours": "{n} ঘণ্টা",
  "method.vantage": "পর্যবেক্ষণ-অবস্থান",

  "data.title": "উন্মুক্ত ডেটা",
  "data.lede":
    "এই সাইটের সবকিছু এই ফাইলগুলো থেকেই তৈরি, অন্য কিছু থেকে নয়। এগুলোই ডেটাসেট: নামিয়ে নিন, সংখ্যা যাচাই করুন, এর ওপর কাজ করুন।",
  "data.file": "ফাইল",
  "data.contents": "বিষয়বস্তু",
  "data.meta": "সংস্করণ, সংরক্ষণের সময়সীমা, সর্বশেষ চালনার সময়।",
  "data.coverage": "সব সংবাদমাধ্যম, প্রতিটি ভাষা ও প্রতিটি গোষ্ঠীর মোট হিসাব; অপ্রকাশিত গোষ্ঠী চিহ্নিত।",
  "data.outlets": "পর্যবেক্ষণাধীন সংবাদমাধ্যম: নাম, ভাষা, গোষ্ঠী, ওয়েবসাইট। কোনো সংখ্যা নেই।",
  "data.extraction-health": "গোষ্ঠী অনুযায়ী পাঠ্য নিষ্কাশনের অবস্থা ও ব্যবহৃত মানদণ্ড।",
  "data.capture-volume": "দিনভিত্তিক সংরক্ষিত পাতা ও প্রথম দেখা নিবন্ধ, বাংলাদেশ সময়।",
  "data.schema": "স্কিমা সংস্করণ",
  "data.generated": "তৈরির সময়",
  "data.licence": "লাইসেন্স",
  "data.licenceText": "ডেটাসেট ও এই সাইটের লেখার লাইসেন্স এখনো ঠিক হয়নি। ঠিক না হওয়া পর্যন্ত এখানে প্রকাশের মাধ্যমে কোনো লাইসেন্স দেওয়া হচ্ছে না।",
  "data.contact": "যোগাযোগ",
  "data.contactText": "টেকডাউন ওয়াচ পরিচালনা করে অ্যাক্টিভেট রাইটস।",
  "data.newsrooms": "সংবাদকক্ষের জন্য",
  "data.newsroomsText":
    "আমাদের ক্রলার তার ইউজার-এজেন্টে TakedownWatch নামে ও activaterights.org-এর লিংকসহ নিজের পরিচয় দেয়। এটি কোনো সাইট থেকে প্রতি দুই সেকেন্ডে সর্বোচ্চ একটি পাতা চায়, robots.txt মেনে চলে এবং ক্লাউডফ্লেয়ার যাচাইয়ের মতো প্রবেশ-নিয়ন্ত্রণ এড়ানোর চেষ্টা করে না।",
  "data.rehost": "এই সাইটের প্রতিলিপি",
  "data.rehostText":
    "সাইটটি সাধারণ স্থির ফাইলের সমষ্টি। তৈরি ফোল্ডারটি যেকোনো ওয়েব সার্ভারে কপি করুন বা সরাসরি ডিস্ক থেকে খুলুন; কোনো উপ-পথ থেকে পরিবেশন করলে SITE_BASE ঠিক করে দিন।",

  "footer.dataset": "ডেটাসেট তৈরি",
  "footer.schema": "স্কিমা",
};

const dict: Record<Locale, Record<Key, string>> = { en, bn };

export function t(l: Locale, key: Key, vars: Record<string, string> = {}): string {
  return dict[l][key].replace(/\{(\w+)\}/g, (_, k: string) => vars[k] ?? `{${k}}`);
}

export function isLocale(x: string | undefined): x is Locale {
  return x === "bn" || x === "en";
}

export function otherLocale(l: Locale): Locale {
  return l === "bn" ? "en" : "bn";
}

/** Absolute site path for a route in a locale, honouring the configured base. */
export function href(l: Locale, route: Route): string {
  const base = import.meta.env.BASE_URL.replace(/\/$/, "");
  return `${base}/${l}/${route ? `${route}/` : ""}`;
}

export function asset(path: string): string {
  return `${import.meta.env.BASE_URL.replace(/\/$/, "")}/${path.replace(/^\//, "")}`;
}
