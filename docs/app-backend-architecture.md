# Code2Guide App Backend Architecture

**وضعیت:** طراحی قطعی برای پیاده‌سازی (هنوز کد شل اپ پیاده نشده؛ mock فرانت روی `localStorage` است)  
**مخاطب:** توسعه‌دهنده بک‌اند / فرانت که شل اپ را به API واقعی وصل می‌کند  
**مرتبط:** [`frontend-api-requirements.md`](./frontend-api-requirements.md) · [`roadMap.md`](./roadMap.md)

---

## 1. هدف و مرز سیستم

### 1.1 چه چیزی می‌سازیم؟

یک **لایهٔ اپلیکیشن (App Shell Backend)** که:

- ورک‌اسپیس‌ها را CRUD می‌کند (با soft delete / restore)
- تنظیمات، جاب ایندکس، لاگ فعالیت، و تاریخچهٔ چت را نگه می‌دارد
- فرانت React را از `localStorage` (`c2g.workspaces.v1`) جدا می‌کند
- به لایهٔ دانش موجود (`/ask`, `/index-workspace`, GraphStore, Qdrant) فقط از طریق **مسیر دیسک** و **سرویس‌های موجود** وصل می‌شود

### 1.2 چه چیزی نیست؟

| این لایه | لایه دانش (موجود) |
|----------|-------------------|
| متادیتای اپ، UI shell | گراف کد (Route, Form, API, Entity, …) |
| `.code2guide/app.db` | `.code2guide/index/{workspace_hash}.db` |
| ورک‌اسپیس، settings، jobs، chat | nodes / edges / embeddings |
| SQLAlchemy models اپ | `GraphStore` + `HybridIndexer` |

**قانون طلایی:** هیچ جدول، نود، یا یال دانشی داخل `app.db` ذخیره نمی‌شود.  
`app.db` فقط «کدام فولدر را ایندکس کرده‌ایم / چه تنظیماتی دارد / چه جاب و چتی بوده» را نگه می‌دارد.

### 1.3 تصمیم‌های معماری (ثابت)

| موضوع | تصمیم |
|-------|--------|
| دیتابیس اپ | **SQLite** تک‌فایل: `.code2guide/app.db` |
| ORM | SQLAlchemy 2.0 |
| API style | REST، JSON، prefix `/api/v1` |
| شناسه‌ها | رشتهٔ با پیشوند (`ws_`, `upd_`, …) نه UUID خام |
| زمان‌ها | ISO-8601 UTC با پسوند `Z` (مثلاً `2026-09-20T08:00:00Z`) |
| حذف ورک‌اسپیس | Soft delete (`deleted_at`)؛ hard delete در این فاز تعریف نشده |
| همزمانی جاب | حداکثر یک `update_job` با وضعیت `running` برای هر workspace |
| زبان کد | انگلیسی (نام فایل، کلاس، فیلد DB)؛ پیام‌های کاربری می‌توانند فارسی باشند |

---

## 2. دیاگرام مرزها

```text
┌─────────────────────────────────────────────────────────────┐
│  Frontend (React + Vite)                                     │
│  pages/workspaces, mock → real API client                    │
└───────────────────────────┬─────────────────────────────────┘
                            │ HTTP /api/v1
┌───────────────────────────▼─────────────────────────────────┐
│  FastAPI                                                      │
│  ┌─────────────────────┐   ┌──────────────────────────────┐ │
│  │ App routes          │   │ Knowledge routes (موجود)     │ │
│  │ workspaces          │   │ /ask, /ask-enduser           │ │
│  │ settings / updates  │   │ /index-workspace, /status    │ │
│  │ logs / chat         │   │ /trace, …                    │ │
│  └─────────┬───────────┘   └──────────────┬───────────────┘ │
│            │                              │                   │
│  ┌─────────▼───────────┐   ┌──────────────▼───────────────┐ │
│  │ App services/repos  │   │ agent + knowledge + search   │ │
│  └─────────┬───────────┘   └──────────────┬───────────────┘ │
│            │                              │                   │
│  ┌─────────▼───────────┐   ┌──────────────▼───────────────┐ │
│  │ .code2guide/app.db  │   │ index/{hash}.db + Qdrant     │ │
│  │ (metadata only)     │   │ (code knowledge only)        │ │
│  └─────────────────────┘   └──────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
         workspace.path ──────────────────────────┘
```

`UpdateService` و `ChatService` از `workspaces.path` برای فراخوانی لایهٔ دانش استفاده می‌کنند.

---

## 3. ساختار پوشه‌ها (هدف پیاده‌سازی)

```text
src/
  api/
    main.py                          # موجود — include روترهای جدید
    deps.py                          # Session, service factories
    routes/
      __init__.py                    # APIRouter aggregate
      health.py                      # اختیاری: GET /api/v1/health
      workspaces.py
      workspace_settings.py
      workspace_updates.py
      workspace_logs.py
      workspace_chat.py
      ask.py                         # اختیاری: جابجایی routes موجود
    schemas/                         # DTO = Pydantic v2
      common.py
      workspace.py
      settings.py
      update_job.py
      activity_log.py
      chat.py
  app/                               # دامنه اپ (جدا از knowledge)
    __init__.py
    constants.py
    enums.py
    ids.py
    exceptions.py
    entities/
      __init__.py
      workspace.py
      settings.py
      update_job.py
      activity_log.py
      chatbot.py
      chat_message.py
    services/
      __init__.py
      workspace_service.py
      settings_service.py
      update_service.py
      log_service.py
      chat_service.py
    repositories/
      __init__.py
      workspace_repo.py
      settings_repo.py
      update_job_repo.py
      activity_log_repo.py
      chatbot_repo.py
      chat_message_repo.py
  db/
    __init__.py
    base.py                          # DeclarativeBase, engine
    session.py                       # SessionLocal, get_db
    init_db.py                       # create_all on startup
    models/
      __init__.py
      workspace.py
      settings.py
      update_job.py
      activity_log.py
      chatbot.py
      chat_message.py
  core/
    config.py                        # + app_db_path
  knowledge/                         # دست‌نخورده
  agent/                             # دست‌نخورده
  search/                            # دست‌نخورده
```

### 3.1 جریان لایه

```text
HTTP Request
  → Route (FastAPI)
    → Schema validation (DTO in)
      → Service (قوانین کسب‌وکار)
        → Repository (پرس‌وجو)
          → ORM Model ↔ SQLite
        ← Entity / نتیجه دامنه
      ← Schema (DTO out)
  → HTTP Response
```

- Route حق دسترسی مستقیم به ORM ندارد.
- Repository حق دانستن HTTP status ندارد.
- Service لایهٔ دانش را صدا می‌زند؛ Repository فقط `app.db` را می‌بیند.

---

## 4. Constants

فایل: `src/app/constants.py`

```python
# Storage
APP_DB_DIR = ".code2guide"
APP_DB_FILENAME = "app.db"
# مسیر کامل پیش‌فرض نسبی ریشهٔ ریپو / cwd سرویس:
# APP_DB_DIR / APP_DB_FILENAME  →  ".code2guide/app.db"

# API
API_V1_PREFIX = "/api/v1"

# ID prefixes (بدون underscore انتهایی؛ underscore در ids.py اضافه می‌شود)
ID_PREFIX_WORKSPACE = "ws"
ID_PREFIX_UPDATE_JOB = "upd"
ID_PREFIX_ACTIVITY_LOG = "log"
ID_PREFIX_CHATBOT = "bot"
ID_PREFIX_MESSAGE = "msg"

# Defaults on workspace create
DEFAULT_AGENT = "guide-agent"
DEFAULT_CHATBOT_USER_ID = "bot_user"
DEFAULT_CHATBOT_USER_NAME = "راهنمای کاربر"
DEFAULT_CHATBOT_TECH_ID = "bot_tech"
DEFAULT_CHATBOT_TECH_NAME = "راهنمای فنی"

# Pagination
DEFAULT_PAGE_LIMIT = 50
MAX_PAGE_LIMIT = 200
DEFAULT_MESSAGE_LIMIT = 100
```

Config (`src/core/config.py`) باید فیلد زیر را داشته باشد:

```python
app_db_path: str = Field(
    default=".code2guide/app.db",
    description="SQLite path for app shell metadata (not knowledge graph)",
)
```

قابل override با env: `APP_DB_PATH`.

---

## 5. Enums

فایل: `src/app/enums.py`  
همه `str, Enum` تا مستقیم در JSON و ستون TEXT بنشینند.

| Enum | مقادیر | استفاده |
|------|--------|---------|
| `WorkspaceStatus` | `idle`, `indexing`, `ready`, `error` | ستون `workspaces.status` |
| `AudienceDefault` | `end_user`, `technical` | settings |
| `UpdateJobStatus` | `running`, `success`, `failed` | `update_jobs.status` |
| `UpdateScope` | `full`, `incremental` | شروع جاب |
| `LogLevel` | `info`, `warn`, `error` | `activity_logs.level` |
| `LogSource` | `system`, `indexer`, `api`, `chat`, `settings` | `activity_logs.source` |
| `ChatRole` | `user`, `assistant` | پیام‌ها |
| `ChatbotRole` | `end_user`, `technical` | نقش بات → انتخاب `/ask` vs `/ask-enduser` |

### 5.1 انتقال وضعیت Workspace

```text
create ──────────────► idle
                         │
         POST …/update   ▼
                      indexing ──success──► ready
                         │
                         └──fail──────────► error
                                              │
                              POST …/update   ▼
                                           indexing → …

soft delete: هر status مجاز → deleted_at set (از لیست active حذف می‌شود)
restore: deleted_at = null (status قبلی حفظ می‌شود مگر قوانین جداگانه)
```

اگر `status == indexing` باشد، شروع جاب جدید → `409 WorkspaceBusyError`.

---

## 6. شناسه‌ها (`ids.py`)

```text
{prefix}_{8_char_base36_or_hex}
مثال: ws_k3m9x2ab , upd_01h8zq2c , log_p9n4w1e0
```

قوانین:

- یکتا در سطح جدول مربوطه (PK)
- پیشوند اجباری؛ فرانت/کلاینت شناسه نمی‌سازد (سرور تولید می‌کند)
- chatbotهای پیش‌فرض می‌توانند id ثابت داشته باشند: `bot_user`, `bot_tech` (در scope یک workspace یکتا؛ PK سراسری بهتر است ترکیبی یا id سراسری یکتا مثل `bot_{ws_short}_{role}`)

**توصیهٔ قطعی برای PK chatbot:**  
`id` سراسری یکتا، مثلاً `bot_k3m9x2ab`، و فیلدهای منطقی `key` اختیاری (`user` / `tech`) — **یا** همان `bot_user` / `bot_tech` به‌شرط unique constraint روی `(workspace_id, id)`.

برای هم‌ترازی با mock فعلی فرانت، این سند فرض می‌کند:

```text
UNIQUE (workspace_id, id) روی chatbots
PK سراسری می‌تواند همان id باشد فقط اگر id در کل DB یکتا بماند.
بهترین شکل عملی:

chatbots.id = "bot_" + random   (PK سراسری)
chatbots.slug = "bot_user" | "bot_tech"   (unique per workspace)

API path همچنان /chatbots/{bot_id} با PK.
Settings.enabled_chatbots به slug یا PK اشاره کند — تصمیم: به **id (PK)** اشاره کند.
```

اگر بخواهیم mock فعلی را بدون تغییر فرانت نگه داریم، `enabled_chatbots: ["bot_user","bot_tech"]` و id همان slug با unique `(workspace_id, id)` کافی است؛ در پیاده‌سازی اولیه همین را بگیرید و در API، `{bot_id}` یعنی همان مقدار داخل همان workspace.

---

## 7. Schema دیتابیس (DDL)

موتور: SQLite · FKها با `PRAGMA foreign_keys = ON` در هر اتصال.

```sql
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS workspaces (
    id           TEXT PRIMARY KEY,
    name         TEXT NOT NULL,
    path         TEXT NOT NULL,
    description  TEXT NOT NULL DEFAULT '',
    status       TEXT NOT NULL DEFAULT 'idle'
                 CHECK (status IN ('idle', 'indexing', 'ready', 'error')),
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL,
    deleted_at   TEXT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_workspaces_path_active
    ON workspaces(path)
    WHERE deleted_at IS NULL;
-- نکته: SQLite partial unique index؛ اگر نسخه/ابزار محدودیت داشت،
-- یکتایی path را در Service برای رکوردهای active enforce کنید.

CREATE INDEX IF NOT EXISTS idx_workspaces_deleted_at
    ON workspaces(deleted_at);
CREATE INDEX IF NOT EXISTS idx_workspaces_status
    ON workspaces(status);
CREATE INDEX IF NOT EXISTS idx_workspaces_updated_at
    ON workspaces(updated_at DESC);

CREATE TABLE IF NOT EXISTS workspace_settings (
    workspace_id       TEXT PRIMARY KEY
                       REFERENCES workspaces(id) ON DELETE CASCADE,
    default_agent      TEXT NOT NULL DEFAULT 'guide-agent',
    enabled_chatbots   TEXT NOT NULL DEFAULT '[]',  -- JSON array of bot ids
    audience_default   TEXT NOT NULL DEFAULT 'end_user'
                       CHECK (audience_default IN ('end_user', 'technical')),
    auto_index         INTEGER NOT NULL DEFAULT 1
                       CHECK (auto_index IN (0, 1)),
    mcp_enabled        INTEGER NOT NULL DEFAULT 0
                       CHECK (mcp_enabled IN (0, 1))
);

CREATE TABLE IF NOT EXISTS update_jobs (
    id            TEXT PRIMARY KEY,
    workspace_id  TEXT NOT NULL
                  REFERENCES workspaces(id) ON DELETE CASCADE,
    started_at    TEXT NOT NULL,
    finished_at   TEXT NULL,
    status        TEXT NOT NULL
                  CHECK (status IN ('running', 'success', 'failed')),
    summary       TEXT NOT NULL DEFAULT '',
    detail        TEXT NOT NULL DEFAULT '',
    rebuild       INTEGER NOT NULL DEFAULT 1
                  CHECK (rebuild IN (0, 1)),
    scope         TEXT NOT NULL DEFAULT 'full'
                  CHECK (scope IN ('full', 'incremental'))
);

CREATE INDEX IF NOT EXISTS idx_update_jobs_ws_started
    ON update_jobs(workspace_id, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_update_jobs_status
    ON update_jobs(status);

CREATE TABLE IF NOT EXISTS activity_logs (
    id            TEXT PRIMARY KEY,
    workspace_id  TEXT NOT NULL
                  REFERENCES workspaces(id) ON DELETE CASCADE,
    at            TEXT NOT NULL,
    level         TEXT NOT NULL
                  CHECK (level IN ('info', 'warn', 'error')),
    source        TEXT NOT NULL,
    message       TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_activity_logs_ws_at
    ON activity_logs(workspace_id, at DESC);
CREATE INDEX IF NOT EXISTS idx_activity_logs_level
    ON activity_logs(workspace_id, level);

CREATE TABLE IF NOT EXISTS chatbots (
    id            TEXT NOT NULL,
    workspace_id  TEXT NOT NULL
                  REFERENCES workspaces(id) ON DELETE CASCADE,
    name          TEXT NOT NULL,
    role          TEXT NOT NULL
                  CHECK (role IN ('end_user', 'technical')),
    PRIMARY KEY (workspace_id, id)
);

CREATE INDEX IF NOT EXISTS idx_chatbots_ws
    ON chatbots(workspace_id);

CREATE TABLE IF NOT EXISTS chat_messages (
    id            TEXT PRIMARY KEY,
    workspace_id  TEXT NOT NULL,
    chatbot_id    TEXT NOT NULL,
    role          TEXT NOT NULL
                  CHECK (role IN ('user', 'assistant')),
    text          TEXT NOT NULL,
    at            TEXT NOT NULL,
    FOREIGN KEY (workspace_id, chatbot_id)
        REFERENCES chatbots(workspace_id, id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_chat_messages_bot_at
    ON chat_messages(workspace_id, chatbot_id, at);
```

### 7.1 نگاشت نوع

| مفهوم | SQLite | Python |
|-------|--------|--------|
| boolean | `INTEGER` 0/1 | `bool` |
| JSON list | `TEXT` | `list[str]` (serialize در repo) |
| datetime | `TEXT` ISO-8601 | `datetime` یا `str` (ترجیح: نگه داشتن str UTC در مرز API) |
| enum | `TEXT` + CHECK | `str, Enum` |

### 7.2 فایل روی دیسک

```text
.code2guide/
  app.db                 ← این سند
  index/
    a1b2c3d4e5f6.db      ← GraphStore per workspace (موجود)
```

هر دو می‌توانند gitignore شوند؛ schema اپ با `init_db` / `create_all` ساخته می‌شود.

---

## 8. Domain Entities

فایل‌ها زیر `src/app/entities/`. ترجیحاً `@dataclass(slots=True)` یا Pydantic مدل داخلی — **جدا از DTO API**.

### 8.1 `WorkspaceEntity`

| فیلد | نوع | توضیح |
|------|-----|--------|
| `id` | `str` | `ws_…` |
| `name` | `str` | نمایشی |
| `path` | `str` | مسیر مطلق یا نسبی ریشهٔ کد هدف |
| `description` | `str` | |
| `status` | `WorkspaceStatus` | |
| `created_at` | `str` | ISO UTC |
| `updated_at` | `str` | ISO UTC |
| `deleted_at` | `str \| None` | |

### 8.2 `WorkspaceSettingsEntity`

| فیلد | نوع |
|------|-----|
| `workspace_id` | `str` |
| `default_agent` | `str` |
| `enabled_chatbots` | `list[str]` |
| `audience_default` | `AudienceDefault` |
| `auto_index` | `bool` |
| `mcp_enabled` | `bool` |

### 8.3 `UpdateJobEntity`

| فیلد | نوع |
|------|-----|
| `id` | `str` |
| `workspace_id` | `str` |
| `started_at` | `str` |
| `finished_at` | `str \| None` |
| `status` | `UpdateJobStatus` |
| `summary` | `str` |
| `detail` | `str` |
| `rebuild` | `bool` |
| `scope` | `UpdateScope` |

### 8.4 `ActivityLogEntity`

| فیلد | نوع |
|------|-----|
| `id` | `str` |
| `workspace_id` | `str` |
| `at` | `str` |
| `level` | `LogLevel` |
| `source` | `str` (ترجیحاً `LogSource`) |
| `message` | `str` |

### 8.5 `ChatbotEntity`

| فیلد | نوع |
|------|-----|
| `id` | `str` |
| `workspace_id` | `str` |
| `name` | `str` |
| `role` | `ChatbotRole` |

### 8.6 `ChatMessageEntity`

| فیلد | نوع |
|------|-----|
| `id` | `str` |
| `workspace_id` | `str` |
| `chatbot_id` | `str` |
| `role` | `ChatRole` |
| `text` | `str` |
| `at` | `str` |

---

## 9. ORM Models

زیر `src/db/models/` — یک کلاس به ازای جدول.  
نام جدول جمع؛ نام ستون snake_case دقیقاً مطابق DDL.

رابطهٔ پیشنهادی SQLAlchemy:

- `Workspace.setting` → one-to-one `WorkspaceSettings`
- `Workspace.update_jobs` → one-to-many
- `Workspace.activity_logs` → one-to-many
- `Workspace.chatbots` → one-to-many
- `Chatbot.messages` → one-to-many

Mapperهای کمکی در repository:

- `bool` ↔ `0/1`
- `list[str]` ↔ `json.dumps` / `json.loads` برای `enabled_chatbots`

---

## 10. DTOs (Pydantic schemas)

همه پاسخ‌ها از فیلدهای **snake_case** استفاده می‌کنند تا با [`frontend-api-requirements.md`](./frontend-api-requirements.md) یکی باشند.  
فرانت فعلی mock گاهی camelCase دارد؛ لایهٔ client فرانت مسئول نگاشت است (یا بعداً `alias`).

### 10.1 Common — `schemas/common.py`

```text
PaginatedResponse[T]
  items: list[T]
  total: int
  limit: int
  offset: int

ErrorBody
  code: str          # مثلاً WORKSPACE_NOT_FOUND
  message: str       # انسان‌خوان
  detail: Any | None
```

Query مشترک صفحه‌بندی:

```text
limit: int = 50  (1..MAX_PAGE_LIMIT)
offset: int = 0  (>= 0)
```

### 10.2 Workspace — `schemas/workspace.py`

| Schema | فیلدها |
|--------|--------|
| `WorkspaceCreate` | `name: str` (min 1), `path: str` (min 1), `description: str = ""` |
| `WorkspaceUpdate` | همه Optional: `name?`, `path?`, `description?` (حداقل یک فیلد) |
| `WorkspaceOut` | `id`, `name`, `path`, `description`, `status`, `updated_at`, `deleted_at` |
| `WorkspaceDetailOut` | `WorkspaceOut` + `settings: WorkspaceSettingsOut` + اختیاری `created_at` |
| `WorkspaceListOut` | `items: list[WorkspaceOut]`, `total: int` (+ بهتر است `limit`/`offset`) |

### 10.3 Settings — `schemas/settings.py`

| Schema | فیلدها |
|--------|--------|
| `WorkspaceSettingsIn` | `default_agent`, `enabled_chatbots: list[str]`, `audience_default`, `auto_index`, `mcp_enabled` |
| `WorkspaceSettingsOut` | همان شکل |

`PUT` = replace کامل (نه patch جزئی).

### 10.4 Update job — `schemas/update_job.py`

| Schema | فیلدها |
|--------|--------|
| `UpdateStartIn` | `rebuild: bool = True`, `scope: UpdateScope = full` |
| `UpdateJobAcceptedOut` | `job_id`, `status`, `started_at` |
| `UpdateJobOut` | `id`, `started_at`, `finished_at`, `status`, `summary`, `detail` |
| `UpdateJobListOut` | `items`, `total` |

### 10.5 Activity log — `schemas/activity_log.py`

| Schema | فیلدها |
|--------|--------|
| `ActivityLogOut` | `id`, `at`, `level`, `source`, `message` |
| `ActivityLogListOut` | paginated |

Query: `level?`, `q?` (substring روی message), `from?`, `to?` (ISO), `limit`, `offset`.

### 10.6 Chat — `schemas/chat.py`

| Schema | فیلدها |
|--------|--------|
| `ChatbotOut` | `id`, `name`, `role` |
| `ChatbotListOut` | `items: list[ChatbotOut]` |
| `ChatMessageOut` | `id`, `role`, `text`, `at` |
| `ChatMessageListOut` | paginated |
| `SendMessageIn` | `text: str` (min 1, strip) |
| `SendMessageOut` | `user_message: ChatMessageOut`, `assistant_message: ChatMessageOut` |

---

## 11. Exceptions

فایل: `src/app/exceptions.py`

| کلاس | HTTP | `code` پیشنهادی |
|------|------|------------------|
| `AppError` | پایه | — |
| `NotFoundError` | 404 | `WORKSPACE_NOT_FOUND`, `JOB_NOT_FOUND`, `CHATBOT_NOT_FOUND` |
| `ConflictError` | 409 | `PATH_ALREADY_EXISTS`, `ALREADY_DELETED`, `NOT_DELETED` |
| `WorkspaceBusyError` | 409 | `WORKSPACE_INDEXING` |
| `ValidationAppError` | 422 | `INVALID_PATH`, `EMPTY_TEXT`, `INVALID_SETTINGS` |

Handler سراسری در FastAPI → `ErrorBody`.

عملیات روی workspace حذف‌شده (به‌جز restore و list deleted):

- پیش‌فرض: `404` (مثل «وجود ندارد» برای کلاینت عادی)
- یا `409 ALREADY_DELETED` اگر بخواهید صریح باشد — **انتخاب این سند: 404 برای mutate روی deleted، به‌جز `POST …/restore`**

---

## 12. Repositories

هر repo فقط Session می‌گیرد و Entity برمی‌گرداند/می‌نویسد.

| Repository | متدهای کلیدی |
|------------|----------------|
| `WorkspaceRepository` | `create`, `get`, `list_active`, `list_deleted`, `update`, `soft_delete`, `restore`, `get_by_path_active` |
| `SettingsRepository` | `get`, `upsert`, `create_defaults` |
| `UpdateJobRepository` | `create`, `get`, `list_by_workspace`, `set_finished`, `has_running` |
| `ActivityLogRepository` | `append`, `list_filtered` |
| `ChatbotRepository` | `create_many`, `list_by_workspace`, `get` |
| `ChatMessageRepository` | `create`, `list_by_bot` |

---

## 13. Services و قوانین کسب‌وکار

### 13.1 `WorkspaceService`

**create**

1. نرمال‌سازی `path` (strip؛ resolve اختیاری با `Path.resolve()` — اگر resolve می‌کنید، همان را ذخیره کنید تا با GraphStore یکی باشد)
2. رد اگر path خالی یا (در حالت سخت) مسیر وجود ندارد → 422
3. رد اگر workspace active با همان path هست → 409
4. درج workspace با `status=idle`
5. `SettingsService.create_defaults`
6. ساخت دو chatbot پیش‌فرض (`bot_user` / `bot_tech`)
7. `LogService.append` سطح info منبع system: «Workspace ساخته شد»
8. برگرداندن `WorkspaceOut`

**list active / deleted**

- فیلتر `q` روی `name` و `path` و `description` (LIKE case-insensitive)
- فیلتر `status` فقط برای active
- مرتب‌سازی: `updated_at DESC` (active) · `deleted_at DESC` (deleted)

**update (PATCH)**

- اگر `path` عوض شد: همان یکتایی active
- `updated_at` را تازه کنید
- لاگ activity اختیاری: «ویرایش شد»

**soft delete**

- set `deleted_at = now`
- اگر جاب `running` دارد: یا fail کردن جاب، یا رد با 409 — **انتخاب این سند: اجازهٔ soft delete + جاب running همچنان تمام می‌شود ولی workspace در UI نیست؛ بهتر است قبلش 409 Busy اگر running است**

**restore**

- فقط اگر `deleted_at` set باشد
- clear `deleted_at`، bump `updated_at`
- لاگ: «بازیابی شد»

### 13.2 `SettingsService`

- `GET`: 404 اگر workspace نباشد
- `PUT`: replace کامل؛ اعتبارسنجی که `enabled_chatbots` زیر‌مجموعهٔ chatbotهای موجود باشد
- تغییر settings → activity log منبع `settings`

### 13.3 `UpdateService`

**start**

1. Workspace باید active باشد
2. اگر `has_running` → 409 Busy
3. بساز `update_job` با `running`
4. `workspace.status = indexing`
5. activity: «ایندکس شروع شد»
6. اجرای ایندکس:
   - **همگام (فاز ۱):** در همان request (ممکن است طولانی باشد) — ساده‌ترین شروع
   - **ناهمگام (فاز ۲):** BackgroundTasks / thread؛ API همان `202` را سریع برگرداند
7. فراخوانی لایهٔ دانش: معادل `POST /index-workspace` با `workspace_path=ws.path`, `rebuild=…`
8. پایان موفق: `status=success`, `summary`/`detail` از نتیجهٔ indexer، `workspace.status=ready`
9. پایان ناموفق: `status=failed`, `workspace.status=error`, level=error در logs
10. پاسخ فوری `202` با `job_id` (حتی در حالت همگام، بعد از اتمام هم می‌توان 200 با job کامل داد؛ **قرارداد API شل: 202 Accepted**)

**list / get**

- newest first
- get باید به همان `workspace_id` تعلق داشته باشد وگرنه 404

### 13.4 `LogService`

- `append` داخلی (سرویس‌های دیگر صدا می‌زنند)
- `list` عمومی با فیلتر

### 13.5 `ChatService`

**list bots / messages** — واضح.

**send message**

1. Validate bot متعلق به workspace و در `enabled_chatbots` (اگر غیرفعال → 422 یا 403)
2. ذخیره پیام user
3. بر اساس `chatbot.role`:
   - `end_user` → منطق `ask-enduser`
   - `technical` → منطق `ask`
4. `workspace_path` از رکورد workspace
5. ذخیره پیام assistant (متن guide)
6. برگرداندن هر دو پیام
7. activity اختیاری با منبع `chat`

خطای LLM/agent → 502 یا 500 با `code=GUIDE_FAILED`؛ پیام user می‌تواند commit شده بماند یا در تراکنش rollback شود — **انتخاب این سند: user را commit کن، assistant را ننویس، و error برگردان (یا assistant با متن خطای مودبانه ذخیره کن)**. ترجیح عملی: rollback کل send اگر guide ساخته نشد تا UI ناسازگار نباشد.

---

## 14. فهرست کامل API

Base path: `/api/v1`  
Content-Type: `application/json`

### 14.1 Health (اختیاری ولی توصیه‌شده)

| Method | Path | Status | توضیح |
|--------|------|--------|--------|
| `GET` | `/health` | 200 | `{ "status": "ok", "app_db": true }` |

### 14.2 Workspaces

| Method | Path | Status | Request | Response |
|--------|------|--------|---------|----------|
| `GET` | `/workspaces` | 200 | Query: `q`, `status`, `limit`, `offset` | `WorkspaceListOut` |
| `GET` | `/workspaces/deleted` | 200 | Query: `q`, `limit`, `offset` | `WorkspaceListOut` |
| `GET` | `/workspaces/{id}` | 200 / 404 | — | `WorkspaceDetailOut` |
| `POST` | `/workspaces` | 201 / 409 / 422 | `WorkspaceCreate` | `WorkspaceOut` |
| `PATCH` | `/workspaces/{id}` | 200 / 404 / 409 / 422 | `WorkspaceUpdate` | `WorkspaceOut` |
| `DELETE` | `/workspaces/{id}` | 200 / 404 / 409 | — | `WorkspaceOut` (با `deleted_at`) |
| `POST` | `/workspaces/{id}/restore` | 200 / 404 / 409 | — | `WorkspaceOut` |

### 14.3 Settings

| Method | Path | Status | Request | Response |
|--------|------|--------|---------|----------|
| `GET` | `/workspaces/{id}/settings` | 200 / 404 | — | `WorkspaceSettingsOut` |
| `PUT` | `/workspaces/{id}/settings` | 200 / 404 / 422 | `WorkspaceSettingsIn` | `WorkspaceSettingsOut` |

### 14.4 Updates

| Method | Path | Status | Request | Response |
|--------|------|--------|---------|----------|
| `POST` | `/workspaces/{id}/update` | 202 / 404 / 409 | `UpdateStartIn` اختیاری | `UpdateJobAcceptedOut` |
| `GET` | `/workspaces/{id}/updates` | 200 / 404 | pagination | `UpdateJobListOut` |
| `GET` | `/workspaces/{id}/updates/{job_id}` | 200 / 404 | — | `UpdateJobOut` |

### 14.5 Logs

| Method | Path | Status | Request | Response |
|--------|------|--------|---------|----------|
| `GET` | `/workspaces/{id}/logs` | 200 / 404 | `level`, `q`, `from`, `to`, `limit`, `offset` | paginated `ActivityLogOut` |

### 14.6 Chat

| Method | Path | Status | Request | Response |
|--------|------|--------|---------|----------|
| `GET` | `/workspaces/{id}/chatbots` | 200 / 404 | — | `ChatbotListOut` |
| `GET` | `/workspaces/{id}/chatbots/{bot_id}/messages` | 200 / 404 | pagination | `ChatMessageListOut` |
| `POST` | `/workspaces/{id}/chatbots/{bot_id}/messages` | 200 / 404 / 422 / 502 | `SendMessageIn` | `SendMessageOut` |

### 14.7 Knowledge APIs (موجود — خارج از scope اپ DB)

این‌ها عوض نمی‌شوند؛ شل اپ کنارشان زندگی می‌کند:

| Method | Path | نقش |
|--------|------|-----|
| `POST` | `/ask` | راهنمای فنی |
| `POST` | `/ask-enduser` | راهنمای کاربر نهایی |
| `POST` | `/index-workspace` | ایندکس عمیق |
| `GET` | `/index/status` | وضعیت ایندکس دانش |
| `GET` | `/trace` | زنجیره FE↔BE (در صورت فعال) |

`UpdateService` و `ChatService` باید **توابع/سرویس‌های Python داخلی** را صدا بزنند، نه لزوماً HTTP به خودشان (اجتناب از loopback مگر برای سادگی موقت).

---

## 15. نمونهٔ payloadها

### ایجاد workspace

```http
POST /api/v1/workspaces
```

```json
{
  "name": "پنل مناقصات",
  "path": "C:/DargahNew/DargahV3/Dargah/Contracts.Contractors",
  "description": "ریپوی اصلی پیمانکاران"
}
```

> در JSON از `/` یا `\\` برای مسیر ویندوز استفاده کنید؛ بک‌اسلش تکی escape است.

```json
{
  "id": "ws_k3m9x2ab",
  "name": "پنل مناقصات",
  "path": "C:\\DargahNew\\DargahV3\\Dargah\\Contracts.Contractors",
  "description": "ریپوی اصلی پیمانکاران",
  "status": "idle",
  "updated_at": "2026-09-20T09:15:00Z",
  "deleted_at": null
}
```

### شروع آپدیت

```http
POST /api/v1/workspaces/ws_k3m9x2ab/update
```

```json
{ "rebuild": true, "scope": "full" }
```

```json
{
  "job_id": "upd_01h8zq2c",
  "status": "running",
  "started_at": "2026-09-20T09:16:00Z"
}
```

### ارسال پیام چت

```http
POST /api/v1/workspaces/ws_k3m9x2ab/chatbots/bot_user/messages
```

```json
{ "text": "چطور مناقصه ثبت کنم؟" }
```

```json
{
  "user_message": {
    "id": "msg_a1",
    "role": "user",
    "text": "چطور مناقصه ثبت کنم؟",
    "at": "2026-09-20T09:20:00Z"
  },
  "assistant_message": {
    "id": "msg_a2",
    "role": "assistant",
    "text": "…راهنمای فارسی…",
    "at": "2026-09-20T09:20:05Z"
  }
}
```

---

## 16. وابستگی‌ها و استارت‌آپ

### 16.1 پکیج‌های لازم (اگر در پروژه نیست)

- `sqlalchemy>=2.0`
- (اختیاری) `greenlet` اگر async session خواستید — این سند **sync Session** را پیش‌فرض می‌گیرد

### 16.2 Lifecycle

در `main.py` lifespan / startup:

1. `Path(settings.app_db_path).parent.mkdir(parents=True, exist_ok=True)`
2. `init_db()` → `Base.metadata.create_all`
3. `PRAGMA foreign_keys=ON` روی connect event

Shutdown: dispose engine.

### 16.3 Dependency Injection

```text
get_db() -> Iterator[Session]
get_workspace_service(db) -> WorkspaceService
…
```

---

## 17. نگاشت فرانت (mock → API)

| UI / mock | API |
|-----------|-----|
| `listActiveWorkspaces` | `GET /workspaces` |
| `listDeletedWorkspaces` | `GET /workspaces/deleted` |
| `getWorkspace` | `GET /workspaces/{id}` |
| `createWorkspace` | `POST /workspaces` |
| `updateWorkspace` | `PATCH /workspaces/{id}` |
| `softDeleteWorkspace` | `DELETE /workspaces/{id}` |
| `restoreWorkspace` | `POST /workspaces/{id}/restore` |
| `saveWorkspaceSettings` | `PUT /workspaces/{id}/settings` |
| `runMockUpdate` | `POST …/update` + poll `GET …/updates/{id}` |
| `activityLogs` | `GET …/logs` |
| chatbots / messages | chat endpoints |

پس از wiring، کلید `c2g.workspaces.v1` حذف یا فقط به‌عنوان cache کوتاه‌مدت اختیاری می‌ماند.

جزئیات قرارداد JSON اولیه: [`frontend-api-requirements.md`](./frontend-api-requirements.md).

---

## 18. امنیت و اعتبارسنجی مسیر (حداقل فاز ۱)

- `path` نباید خالی باشد.
- نرمال‌سازی جداکننده (`\` / `/`) قبل از ذخیرهٔ مقایسه‌ای.
- در فاز ۱ نیازی به sandbox سخت نیست (اپ لوکال/اپراتوری است)، ولی:
  - از path traversal عمدی روی مسیرهای داخلی خود سرویس جلوگیری کنید
  - هرگز محتوای `app.db` را با ورودی کاربر به‌عنوان SQL خام نسازید (ORM/bind params)
- Auth/multi-tenant خارج از scope این سند است (تک‌اپراتور).

---

## 19. تست

| لایه | چه چیزی |
|------|---------|
| Unit repo | CRUD + soft delete + unique path |
| Unit service | Busy indexing، restore قوانین، defaults روی create |
| API integration | TestClient FastAPI + فایل SQLite موقت |
| Contract | shape پاسخ‌ها مطابق schemas |

فایل‌های پیشنهادی:

```text
tests/app/test_workspace_service.py
tests/app/test_workspaces_api.py
tests/app/test_update_service.py
tests/app/test_chat_service.py
```

---

## 20. ترتیب پیاده‌سازی پیشنهادی

1. **Config + db package** — engine، models، `init_db`
2. **enums / constants / ids / exceptions / entities**
3. **Repositories** — workspaces + settings
4. **WorkspaceService + routes CRUD** (+ soft delete/restore)
5. **Settings routes**
6. **Activity logs** (append از create/delete)
7. **Update jobs** + اتصال به `index-workspace` داخلی
8. **Chatbots + messages** + اتصال به ask / ask-enduser
9. **Frontend client** جایگزین mock
10. **تست‌های integration** و حذف وابستگی UI به localStorage

هر استپ باید به‌تنهایی قابل دمو روی `/docs` سوگر FastAPI باشد.

---

## 21. خارج از scope (عمداً بعداً)

مطابق بخش Future در requirements فرانت؛ در `app.db` فعلی جدول نسازید مگر نیاز واقعی:

- Agents registry جدا
- MCP server registry
- Pipeline runs عمومی
- Auth / کاربران / نقش‌ها
- Hard delete + پاک کردن فایل‌های `index/{hash}.db` و collection کوادرانت
- اشتراک‌گذاری ورک‌اسپیس بین چند اپراتور

وقتی hard delete اضافه شد، باید صریحاً cleanup دانش را هم تعریف کنید — امروز soft delete فقط متادیتا را پنهان می‌کند و ایندکس روی دیسک می‌ماند.

---

## 22. چک‌لیست پذیرش (Definition of Done)

- [ ] `.code2guide/app.db` با جداول بالا ساخته می‌شود
- [ ] هیچ جدول دانش داخل `app.db` نیست
- [ ] همه endpointهای بخش 14.2–14.6 روی OpenAPI دیده می‌شوند
- [ ] Create → دو chatbot + settings + یک activity log
- [ ] Soft delete از `GET /workspaces` حذف می‌کند و در `…/deleted` می‌آید
- [ ] Restore برعکس کار می‌کند
- [ ] Update جاب status ورک‌اسپیس را `indexing` → `ready`/`error` می‌کند
- [ ] Chat بر اساس role بات، guide درست را برمی‌گرداند و پیام‌ها persist می‌شوند
- [ ] فرانت می‌تواند بدون `localStorage` لیست ورک‌اسپیس را نشان دهد

---

## 23. خلاصهٔ یک‌صفحه‌ای

```text
App DB     = SQLite .code2guide/app.db
Knowledge  = SQLite per-hash + Qdrant (جدا)
Layers     = routes → schemas → services → repos → ORM
Core nouns = Workspace, Settings, UpdateJob, ActivityLog, Chatbot, ChatMessage
API        = /api/v1/workspaces[+ settings|updates|logs|chatbots]
IDs        = ws_ / upd_ / log_ / bot_ / msg_
Delete     = soft (deleted_at)
Index hook = UpdateService → existing indexer(path)
Chat hook  = ChatService → existing ask / ask-enduser(path)
```

این سند مرجع پیاده‌سازی بک‌اند شل است؛ در صورت تعارض جزئی با mock فرانت، **snake_case و قرارداد این سند + `frontend-api-requirements.md` مقدم است** و فرانت adapt می‌شود.
