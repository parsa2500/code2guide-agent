# نقشه راه تسلط کامل بر سیستم (Full-System Mastery)

هدف: تبدیل `code2guide-agent` از یک راهنمای محدود UX فرانت، به سیستمی که **کل فرانت + کل بک + رابطه بین آن‌ها + دیتابیس** را ایندکس و پارس کند، و بتوان با سؤال آزاد از آن پرسید.

---

## وضعیت فعلی (مبدأ)

| قابلیت | وضعیت |
|---|---|
| اسکن روت/منوی فرانت | آماده (`RouteExtractor`) |
| جستجوی لیبل فارسی | آماده (ایندکس + ripgrep fallback) |
| پارس فرم/دکمه JSX | آماده؛ ایندکس یک‌باره بدون سقف ۶ |
| ساخت راهنمای UX فارسی | آماده (LLM یا template) |
| ایندکس یک‌باره کل پروژه (فرانت) | آماده (`POST /index-workspace` + `src/knowledge/`) |
| Hybrid / Qdrant در مسیر `/ask` | وصل؛ retrieval-first از گراف + بردار |
| راهنمای کاربر نهایی | آماده (`POST /ask-enduser` — بدون فایل/API/استناد فنی) |
| پارس بک‌اند (API / service / entity / DB) | آماده برای .NET Core و ASP.NET MVC Framework (`src/parsers/dotnet/` + MvcApiParser + BackendIndexer) |
| گراف رابطه فرانت ↔ بک | آماده (`CALLS_API` + `GET /api/v1/trace` + field `MAPS_TO`)؛ AngularJS `$http`/`$resource` هم پشتیبانی می‌شود |
| Q&A آزاد روی کل سیستم | آماده — planner + tools + citations + golden set + incremental skip |

**جمع‌بندی مبدأ:** فاز ۰ تا ۴ انجام شده — ایندکس فرانت+بک .NET، زنجیره end-to-end، Q&A با planner/استناد، و skip-unchanged.

---

## هدف نهایی (مقصد)

1. **ایندکس کامل** یک‌بار (و به‌روزرسانی افزایشی) روی کل workspace
2. **پارس عمیق فرانت:** روت، صفحه، کامپوننت، فرم، دکمه، i18n، state UI
3. **پارس عمیق بک:** route/API، DTO/schema، service/use-case، class/logic، entity/ORM، migration/SQL
4. **Relation ف↔ب:** صفحه → فرم → API call → handler → service → entity → جدول
5. **Q&A مسلط:** هر سؤال (UX، منطق، دیتا، جریان end-to-end) با استناد به فایل/سیمبل

خروجی ذهنی ایده‌آل برای یک جریان:

```text
صفحه «ثبت مناقصه»
  → فرم UI (فیلدها / دکمه ثبت)
  → POST /api/tenders
  → TenderController / route handler
  → TenderService.create(...)
  → Entity Tender
  → جدول tenders (+ relationها)
```

---

## اصول طراحی

- **استخراج قطعی اول، LLM دوم:** اول AST/regex/schema؛ LLM فقط برای توضیح و جمع‌بندی
- **ایندکس ماندگار:** `/ask` روی ایندکس جستجو کند، نه اسکن خام همه‌چیز در هر درخواست
- **گراف دانش + بازیابی هیبرید:** گره‌ها و یال‌ها در store؛ جستجو lexical + semantic (Qdrant)
- **استناد اجباری:** هر ادعا به `file_path` + symbol/line برگردد
- **افزایشی:** re-index فقط فایل‌های تغییرکرده

---

## فازها و استپ‌ها

### فاز ۰ — آماده‌سازی و قراردادها (۱ استپ پایه)

**هدف:** تعریف مدل دادهٔ مشترک قبل از کد زیاد.

- [x] تعریف schema گره‌ها: `Route`, `Page`, `Component`, `FormField`, `ApiEndpoint`, `Service`, `Entity`, `Table`, `Relation`
- [x] تعریف یال‌ها: `renders`, `contains_field`, `calls_api`, `handled_by`, `uses_service`, `persists_to`, `fk_to`
- [x] انتخاب store: Qdrant (بردار) + JSON/SQLite برای گراف صریح
- [x] قرارداد API جدید: `POST /index-workspace`, `GET /index/status`, ارتقای `/ask`

**خروجی فاز:** سند مدل داده + interfaceهای Python در `src/knowledge/`.

---

### فاز ۱ — ایندکس کامل فرانت (عمق UI/UX)

**هدف:** برداشتن سقف ۶ فایل؛ یک‌بار کل فرانت را بفهمد.

1. **Endpoint ایندکس** ✅
   - `POST /api/v1/index-workspace` با `workspace_path`
   - اسکن کامل روت‌ها (همان `RouteExtractor`، بدون فیلتر query)
2. **پارس عمیق همه صفحات/کامپوننت‌های UI** ✅
   - همه `.tsx/.jsx/.vue` مرتبط با روت + فرم
   - سقف ۶ حذف؛ `AST_INSPECT_LIMIT` فقط برای fallback در `/ask`
3. **استخراج i18n و لیبل‌ها** ✅
   - فایل‌های ترجمه + stringهای فارسی داخل JSX
4. **نوشتن در ایندکس** ✅
   - اتصال واقعی `HybridIndexer` به pipeline ایندکس
   - ذخیره metadata فرم/فیلد/دکمه/breadcrumb در SQLite + بردار
5. **تغییر `/ask`** ✅
   - اول retrieval از ایندکس، بعد synthesize راهنما

**معیار آمادگی فاز ۱:** روی یک ریپوی فرانت نمونه، `index-workspace` همه روت‌ها را برگرداند و `/ask` بدون rescan کامل جواب بدهد. ✅ (`sample_workspace`)

---

### فاز ۲ — پارس بک‌اند (منطق + کلاس + entity + DB)

**هدف:** بک را مثل فرانت، ساختاریافته بفهمد. ✅ برای .NET

1. **کشف استک بک** ✅ — `StackDetector` (.NET via `.csproj`/Controllers/…)
2. **استخراج API surface** ✅ — Controllers + Minimal APIs + OpenAPI merge
3. **استخراج لایه دامنه** ✅ — `*Service` / `*Handler` / `*UseCase`
4. **استخراج مدل داده** ✅ — EF entities + Migrations → `Table`
5. **ایندکس بک** ✅ — همان SQLite graph + hybrid؛ پاسخ `/ask` برای سؤال بک

**معیار آمادگی فاز ۲:** سؤال‌هایی مثل «entity مناقصه چه فیلدهایی دارد؟» یا «کدام سرویس create می‌کند؟» با استناد جواب داده شود. ✅ (`sample_workspace/backend`)

---

### فاز ۳ — رابطه فرانت ↔ بک (Trace)

**هدف:** جریان end-to-end را وصل کند. ✅

1. **Tracer سمت فرانت** ✅ — `FrontendApiTracer` (fetch/axios/RQ)
2. **Tracer سمت بک** ✅ — یال‌های `HANDLED_BY` / `USES_SERVICE` / `PERSISTS_TO`
3. **لینک فرم ↔ payload** ✅ — `FieldLinker` + `MAPS_TO`
4. **لینک entity ↔ جدول** ✅ — از فاز ۲ + تأیید در trace
5. **API برای جریان** ✅ — `GET /api/v1/trace?from=…`

**معیار آمادگی فاز ۳:** برای یک صفحه کلیدی، زنجیره Page → API → Service → Entity → Table ساخته شود. ✅ (`/tenders/create`)

---

### فاز ۴ — Q&A مسلط روی کل سیستم

**هدف:** «هر سؤالی» در محدودهٔ ایندکس‌شده، قابل پاسخ باشد. ✅

1. **ابزارهای agent** ✅
   - `search_code`, `get_route`, `get_api`, `get_entity`, `get_table`, `trace_flow`
2. **Planner چندمرحله‌ای** ✅
   - تشخیص نوع سؤال: UX / API / دیتا / جریان کامل (`src/agent/planner.py`)
3. **پاسخ با استناد** ✅
   - همیشه فایل + سیمبل؛ ممنوعیت حدس بدون منبع (`tool_evidence`)
4. **ارزیابی** ✅
   - مجموعه سؤال طلایی (`tests/golden/sample_workspace_qa.json` + `test_golden_qa.py`)
5. **بازایندیس افزایشی** ✅
   - hash فایل‌ها برای skip-unchanged وقتی `rebuild=false` (`src/knowledge/incremental.py`)

**معیار آمادگی فاز ۴:** دقت قابل قبول روی golden set برای سؤال‌های UX، منطق، و end-to-end. ✅

---

## ترتیب اجرا (خلاصه استپ‌به‌استپ)

| # | استپ | فاز |
|---|---|---|
| 1 | تعریف schema گراف دانش | ۰ ✅ |
| 2 | `POST /index-workspace` + اسکن کامل روت فرانت | ۱ ✅ |
| 3 | پارس عمیق همه UI forms (بدون سقف ۶) | ۱ ✅ |
| 4 | وصل Qdrant/Hybrid به ایندکس و `/ask` | ۱ ✅ |
| 5 | پارسر API بک (.NET) | ۲ ✅ |
| 6 | پارسر service/class | ۲ ✅ |
| 7 | پارسر entity + DB schema | ۲ ✅ |
| 8 | Tracer فراخوانی ف↔ب | ۳ ✅ |
| 9 | لینک فیلد فرم ↔ DTO ↔ ستون | ۳ ✅ |
| 10 | ابزارهای Q&A + planner | ۴ ✅ |
| 11 | golden set + ایندکس افزایشی | ۴ ✅ |

---

## وابستگی‌ها و پیش‌نیاز عملی

- مسیر workspace قابل دسترس برای سرویس (`TARGET_WORKSPACE_PATH` یا `workspace_path`)
- برای کیفیت توضیح: `OPENROUTER_API_KEY` (اختیاری برای استخراج؛ مفید برای پاسخ)
- برای semantic search: Qdrant (`docker compose up`) + در صورت نیاز `GOOGLE_API_KEY`
- مشخص بودن استک بک‌اند هدف: **.NET** (ASP.NET Core و ASP.NET MVC Framework + AngularJS ui-router پیاده‌سازی‌شده)؛ استک‌های دیگر بعداً به‌صورت پلاگین

---

## ریسک‌ها

| ریسک | اثر | کاهش |
|---|---|---|
| تنوع فریم‌ورک بک/فرانت | پارسر عمومی ضعیف می‌شود | پلاگین per-stack |
| کد dynamic (string URL، reflection) | miss در tracer | heuristic + LLM فقط برای پیشنهاد لینک مشکوک |
| ریپوی خیلی بزرگ | ایندکس کند/گران | ایندکس افزایشی + ignore patterns |
| نام‌گذاری ناسازگار UI↔API | لینک فیلدها شکننده | similarity + schema overlap |

---

## تعریف «رسیدیم»

وقتی هر سه مورد زیر برقرار باشد:

1. یک `index-workspace` کل فرانت و بک هدف را بدون سقف مصنوعی پارس کند  
2. برای صفحات اصلی، `trace` زنجیره UI → API → منطق → DB را برگرداند  
3. `/ask` به سؤال‌های UX، منطق، و دیتا با استناد فایل جواب بدهد  

---

## قدم بعدی پیشنهادی بعد از این سند

فاز ۰ تا ۴ پیاده‌سازی شده‌اند (`QueryPlanner`, ابزارهای cited، golden set، `FileHashManifest`).

قدم بعدی (اختیاری): partial reindex per-file، watch daemon، یا پارسر استک غیر-.NET.

لایهٔ ASP.NET MVC Framework + Razor + AngularJS ui-router اضافه شده (`MvcApiParser`, `RazorNgFormVisitor`, fixture در `sample_workspace/mvc_portal`).
