export type WorkspaceStatus = "ready" | "indexing" | "error" | "idle";

export interface Workspace {
  id: string;
  name: string;
  path: string;
  description: string;
  status: WorkspaceStatus;
  updatedAt: string;
  deletedAt: string | null;
  settings: WorkspaceSettings;
  updateLogs: UpdateLog[];
  activityLogs: ActivityLog[];
  chatbots: Chatbot[];
}

export interface WorkspaceSettings {
  defaultAgent: string;
  enabledChatbots: string[];
  audienceDefault: "end_user" | "technical";
  autoIndex: boolean;
  mcpEnabled: boolean;
}

export interface UpdateLog {
  id: string;
  startedAt: string;
  finishedAt: string | null;
  status: "running" | "success" | "failed";
  summary: string;
  detail: string;
}

export interface ActivityLog {
  id: string;
  at: string;
  level: "info" | "warn" | "error";
  source: string;
  message: string;
}

export interface Chatbot {
  id: string;
  name: string;
  role: string;
  messages: ChatMessage[];
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  text: string;
  at: string;
}

export type WorkspaceInput = {
  name: string;
  path: string;
  description: string;
};

const STORAGE_KEY = "c2g.workspaces.v1";

function nowIso() {
  return new Date().toISOString();
}

function uid(prefix: string) {
  return `${prefix}_${Math.random().toString(36).slice(2, 10)}`;
}

function seedWorkspaces(): Workspace[] {
  const t = nowIso();
  return [
    {
      id: "ws_sample",
      name: "پنل مناقصات",
      path: "sample_workspace",
      description: "نمونه React + .NET برای دموی راهنمای کاربری",
      status: "ready",
      updatedAt: t,
      deletedAt: null,
      settings: {
        defaultAgent: "guide-agent",
        enabledChatbots: ["bot_user", "bot_tech"],
        audienceDefault: "end_user",
        autoIndex: true,
        mcpEnabled: false,
      },
      updateLogs: [
        {
          id: "upd_1",
          startedAt: t,
          finishedAt: t,
          status: "success",
          summary: "ایندکس اولیه کامل شد",
          detail: "Routes: 12 · Forms: 4 · APIs: 8 · Edges: 35",
        },
      ],
      activityLogs: [
        {
          id: "log_1",
          at: t,
          level: "info",
          source: "indexer",
          message: "Workspace آماده است",
        },
      ],
      chatbots: [
        {
          id: "bot_user",
          name: "راهنمای کاربر",
          role: "end_user",
          messages: [
            {
              id: "m1",
              role: "assistant",
              text: "سلام! بپرسید چه کاری می‌خواهید در سامانه انجام دهید.",
              at: t,
            },
          ],
        },
        {
          id: "bot_tech",
          name: "راهنمای فنی",
          role: "technical",
          messages: [
            {
              id: "m2",
              role: "assistant",
              text: "آماده پاسخ فنی با مسیر و فرم هستم.",
              at: t,
            },
          ],
        },
      ],
    },
    {
      id: "ws_portal",
      name: "پورتال MVC",
      path: "sample_workspace/mvc_portal",
      description: "پورتال قدیمی ASP.NET MVC",
      status: "idle",
      updatedAt: t,
      deletedAt: null,
      settings: {
        defaultAgent: "guide-agent",
        enabledChatbots: ["bot_user"],
        audienceDefault: "technical",
        autoIndex: false,
        mcpEnabled: true,
      },
      updateLogs: [],
      activityLogs: [
        {
          id: "log_2",
          at: t,
          level: "warn",
          source: "system",
          message: "هنوز ایندکس نشده",
        },
      ],
      chatbots: [
        {
          id: "bot_user",
          name: "راهنمای کاربر",
          role: "end_user",
          messages: [],
        },
      ],
    },
  ];
}

function readAll(): Workspace[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) {
      const seed = seedWorkspaces();
      writeAll(seed);
      return seed;
    }
    return JSON.parse(raw) as Workspace[];
  } catch {
    const seed = seedWorkspaces();
    writeAll(seed);
    return seed;
  }
}

function writeAll(list: Workspace[]) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(list));
}

function bump(ws: Workspace, patch: Partial<Workspace>): Workspace {
  return { ...ws, ...patch, updatedAt: nowIso() };
}

export function listActiveWorkspaces(): Workspace[] {
  return readAll()
    .filter((w) => !w.deletedAt)
    .sort((a, b) => b.updatedAt.localeCompare(a.updatedAt));
}

export function listDeletedWorkspaces(): Workspace[] {
  return readAll()
    .filter((w) => !!w.deletedAt)
    .sort((a, b) => (b.deletedAt || "").localeCompare(a.deletedAt || ""));
}

export function getWorkspace(id: string): Workspace | undefined {
  return readAll().find((w) => w.id === id);
}

export function createWorkspace(input: WorkspaceInput): Workspace {
  const list = readAll();
  const t = nowIso();
  const ws: Workspace = {
    id: uid("ws"),
    name: input.name.trim(),
    path: input.path.trim(),
    description: input.description.trim(),
    status: "idle",
    updatedAt: t,
    deletedAt: null,
    settings: {
      defaultAgent: "guide-agent",
      enabledChatbots: ["bot_user"],
      audienceDefault: "end_user",
      autoIndex: false,
      mcpEnabled: false,
    },
    updateLogs: [],
    activityLogs: [
      {
        id: uid("log"),
        at: t,
        level: "info",
        source: "workspace",
        message: "Workspace ساخته شد",
      },
    ],
    chatbots: [
      {
        id: "bot_user",
        name: "راهنمای کاربر",
        role: "end_user",
        messages: [],
      },
    ],
  };
  writeAll([ws, ...list]);
  return ws;
}

export function updateWorkspace(id: string, input: WorkspaceInput): Workspace | undefined {
  const list = readAll();
  const idx = list.findIndex((w) => w.id === id);
  if (idx < 0) return undefined;
  const next = bump(list[idx], {
    name: input.name.trim(),
    path: input.path.trim(),
    description: input.description.trim(),
  });
  next.activityLogs = [
    {
      id: uid("log"),
      at: nowIso(),
      level: "info",
      source: "workspace",
      message: "اطلاعات workspace ویرایش شد",
    },
    ...next.activityLogs,
  ];
  list[idx] = next;
  writeAll(list);
  return next;
}

export function softDeleteWorkspace(id: string): Workspace | undefined {
  const list = readAll();
  const idx = list.findIndex((w) => w.id === id);
  if (idx < 0) return undefined;
  const next = bump(list[idx], { deletedAt: nowIso() });
  next.activityLogs = [
    {
      id: uid("log"),
      at: nowIso(),
      level: "warn",
      source: "workspace",
      message: "Workspace به سطل حذف منتقل شد",
    },
    ...next.activityLogs,
  ];
  list[idx] = next;
  writeAll(list);
  return next;
}

export function restoreWorkspace(id: string): Workspace | undefined {
  const list = readAll();
  const idx = list.findIndex((w) => w.id === id);
  if (idx < 0) return undefined;
  const next = bump(list[idx], { deletedAt: null });
  next.activityLogs = [
    {
      id: uid("log"),
      at: nowIso(),
      level: "info",
      source: "workspace",
      message: "Workspace بازیابی شد",
    },
    ...next.activityLogs,
  ];
  list[idx] = next;
  writeAll(list);
  return next;
}

export function saveWorkspaceSettings(
  id: string,
  settings: WorkspaceSettings,
): Workspace | undefined {
  const list = readAll();
  const idx = list.findIndex((w) => w.id === id);
  if (idx < 0) return undefined;
  const next = bump(list[idx], { settings });
  next.activityLogs = [
    {
      id: uid("log"),
      at: nowIso(),
      level: "info",
      source: "settings",
      message: "تنظیمات ذخیره شد",
    },
    ...next.activityLogs,
  ];
  list[idx] = next;
  writeAll(list);
  return next;
}

export function runMockUpdate(id: string): Workspace | undefined {
  const list = readAll();
  const idx = list.findIndex((w) => w.id === id);
  if (idx < 0) return undefined;
  const started = nowIso();
  const log: UpdateLog = {
    id: uid("upd"),
    startedAt: started,
    finishedAt: started,
    status: "success",
    summary: "آپدیت mock انجام شد",
    detail:
      "اسکن فرانت و بک شبیه‌سازی شد.\nRoutes +2 · Forms +0 · APIs +1\nمدت: ~1.2s (mock)",
  };
  const next = bump(list[idx], {
    status: "ready",
    updateLogs: [log, ...list[idx].updateLogs],
  });
  next.activityLogs = [
    {
      id: uid("log"),
      at: started,
      level: "info",
      source: "update",
      message: "آپدیت workspace اجرا شد (mock)",
    },
    ...next.activityLogs,
  ];
  list[idx] = next;
  writeAll(list);
  return next;
}

export function appendChatMessage(
  workspaceId: string,
  botId: string,
  text: string,
): Workspace | undefined {
  const list = readAll();
  const idx = list.findIndex((w) => w.id === workspaceId);
  if (idx < 0) return undefined;
  const ws = list[idx];
  const bots = ws.chatbots.map((b) => {
    if (b.id !== botId) return b;
    const userMsg: ChatMessage = {
      id: uid("m"),
      role: "user",
      text,
      at: nowIso(),
    };
    const reply: ChatMessage = {
      id: uid("m"),
      role: "assistant",
      text: `(mock) دریافت شد: «${text}» — اتصال به بک هنوز فعال نیست.`,
      at: nowIso(),
    };
    return { ...b, messages: [...b.messages, userMsg, reply] };
  });
  const next = bump(ws, { chatbots: bots });
  list[idx] = next;
  writeAll(list);
  return next;
}

export function formatFaDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString("fa-IR");
  } catch {
    return iso;
  }
}
