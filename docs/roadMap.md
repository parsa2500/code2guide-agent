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
| پارس بک‌اند (API / service / entity / DB) | نیست (فاز ۲) |
| گراف رابطه فرانت ↔ بک | نیست (فاز ۳) |
| Q&A آزاد روی کل سیستم | نیست (فاز ۴) |

**جمع‌بندی مبدأ:** فاز ۰ و ۱ انجام شده — کل فرانت را می‌توان یک‌بار ایندکس کرد و `/ask` از ایندکس می‌خواند. بک و tracer ف↔ب هنوز نیست.

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

**هدف:** بک را مثل فرانت، ساختاریافته بفهمد.

1. **کشف استک بک** (پلاگین‌پذیر)
   - مثلاً FastAPI / Django / Nest / Spring / .NET — تشخیص از فایل‌های مشخصه
2. **استخراج API surface**
   - path، method، auth، request/response body
3. **استخراج لایه دامنه**
   - service / use-case / class / functionهای اصلی
4. **استخراج مدل داده**
   - ORM entity، field type، relation (1-1, 1-N, N-N)
   - migration / SQL schema → `Table` nodes
5. **ایندکس بک**
   - همان store گراف + بردار روی docstring/نام سیمبل‌ها

**معیار آمادگی فاز ۲:** سؤال‌هایی مثل «entity مناقصه چه فیلدهایی دارد؟» یا «کدام سرویس create می‌کند؟» با استناد جواب داده شود.

---

### فاز ۳ — رابطه فرانت ↔ بک (Trace)

**هدف:** جریان end-to-end را وصل کند.

1. **Tracer سمت فرانت**
   - پیدا کردن `fetch` / `axios` / React Query / RTK / سرویس‌های API client
   - نگاشت URL/method به `ApiEndpoint`
2. **Tracer سمت بک**
   - از route handler تا service تا repository/entity
3. **لینک فرم ↔ payload**
   - نام فیلد UI ≈ کلید DTO/schema
4. **لینک entity ↔ جدول**
   - از مدل ORM به migration/SQL
5. **API برای جریان**
   - مثلاً `GET /trace?from=page:/tenders/create` → زنجیره کامل

**معیار آمادگی فاز ۳:** برای یک صفحه کلیدی، زنجیره Page → API → Service → Entity → Table ساخته شود.

---

### فاز ۴ — Q&A مسلط روی کل سیستم

**هدف:** «هر سؤالی» در محدودهٔ ایندکس‌شده، قابل پاسخ باشد.

1. **ابزارهای agent**
   - `search_code`, `get_route`, `get_api`, `get_entity`, `get_table`, `trace_flow`
2. **Planner چندمرحله‌ای**
   - تشخیص نوع سؤال: UX / API / دیتا / جریان کامل
3. **پاسخ با استناد**
   - همیشه فایل + سیمبل؛ ممنوعیت حدس بدون منبع
4. **ارزیابی**
   - مجموعه سؤال طلایی (golden set) روی یک پروژه نمونه
5. **بازایندیس افزایشی**
   - watch یا hash فایل‌ها برای update جزئی

**معیار آمادگی فاز ۴:** دقت قابل قبول روی golden set برای سؤال‌های UX، منطق، و end-to-end.

---

## ترتیب اجرا (خلاصه استپ‌به‌استپ)

| # | استپ | فاز |
|---|---|---|
| 1 | تعریف schema گراف دانش | ۰ ✅ |
| 2 | `POST /index-workspace` + اسکن کامل روت فرانت | ۱ ✅ |
| 3 | پارس عمیق همه UI forms (بدون سقف ۶) | ۱ ✅ |
| 4 | وصل Qdrant/Hybrid به ایندکس و `/ask` | ۱ ✅ |
| 5 | پارسر API بک | ۲ |
| 6 | پارسر service/class | ۲ |
| 7 | پارسر entity + DB schema | ۲ |
| 8 | Tracer فراخوانی ف↔ب | ۳ |
| 9 | لینک فیلد فرم ↔ DTO ↔ ستون | ۳ |
| 10 | ابزارهای Q&A + planner | ۴ |
| 11 | golden set + ایندکس افزایشی | ۴ |

---

## وابستگی‌ها و پیش‌نیاز عملی

- مسیر workspace قابل دسترس برای سرویس (`TARGET_WORKSPACE_PATH` یا `workspace_path`)
- برای کیفیت توضیح: `OPENROUTER_API_KEY` (اختیاری برای استخراج؛ مفید برای پاسخ)
- برای semantic search: Qdrant (`docker compose up`) + در صورت نیاز `GOOGLE_API_KEY`
- مشخص بودن استک بک‌اند هدف (برای اولویت پارسر فاز ۲)

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

فاز ۰ و ۱ پیاده‌سازی شده‌اند (`src/knowledge/`, `POST /api/v1/index-workspace`, `/ask` retrieval-first).

قدم بعدی: **فاز ۲** — پارس بک‌اند. استک بک‌اند پروژهٔ هدف را مشخص کنید تا پارسر از روز اول درست انتخاب شود.
