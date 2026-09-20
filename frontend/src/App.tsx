import { useCallback, useEffect, useMemo, useState } from "react";
import type { FormEvent } from "react";
import { marked } from "marked";
import {
  askGuide,
  fetchIndexStatus,
  indexWorkspace,
  normalizeGuideMarkdown,
} from "./api/client";
import type {
  Audience,
  AskResponse,
  IndexResponse,
  IndexStatus,
} from "./api/client";

marked.setOptions({ breaks: true, gfm: true });

type LedState = "idle" | "ok" | "warn" | "run" | "err";

function Led({
  label,
  state,
}: {
  label: string;
  state: LedState;
}) {
  return (
    <span className="led" data-state={state === "idle" ? undefined : state}>
      <span className="led-dot" aria-hidden="true" />
      {label}
    </span>
  );
}

export default function App() {
  const [audience, setAudience] = useState<Audience>("end_user");
  const [workspace, setWorkspace] = useState("");
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("آماده برای پرسش");
  const [statusTone, setStatusTone] = useState<"idle" | "ok" | "error">("idle");
  const [asking, setAsking] = useState(false);
  const [indexing, setIndexing] = useState(false);
  const [guideHtml, setGuideHtml] = useState("");
  const [meta, setMeta] = useState<AskResponse | null>(null);
  const [indexInfo, setIndexInfo] = useState<IndexStatus | null>(null);
  const [lastIndex, setLastIndex] = useState<IndexResponse | null>(null);

  const indexLed: LedState = indexing
    ? "run"
    : lastIndex || indexInfo?.indexed || indexInfo?.exists
      ? "ok"
      : indexInfo
        ? "warn"
        : "idle";

  const askLed: LedState = asking ? "run" : statusTone === "error" ? "err" : meta ? "ok" : "idle";

  const audienceLed: LedState = "ok";

  const emptyCopy = useMemo(
    () =>
      audience === "end_user"
        ? "راهنمای ساده اینجا ظاهر می‌شود. مخاطب را انتخاب کنید، در صورت نیاز ایندکس کنید، بعد بپرسید."
        : "راهنمای فنی با مسیرها و فرم‌ها اینجا می‌آید. پس از ایندکس، پرسش خود را بفرستید.",
    [audience],
  );

  const refreshStatus = useCallback(async () => {
    try {
      const info = await fetchIndexStatus(workspace || undefined);
      setIndexInfo(info);
    } catch {
      setIndexInfo(null);
    }
  }, [workspace]);

  useEffect(() => {
    void refreshStatus();
  }, [refreshStatus]);

  async function onIndex() {
    setIndexing(true);
    setStatus("در حال ایندکس workspace…");
    setStatusTone("idle");
    try {
      const result = await indexWorkspace(workspace || undefined, true);
      setLastIndex(result);
      setStatus(result.message || "ایندکس کامل شد");
      setStatusTone("ok");
      await refreshStatus();
    } catch (err) {
      setStatus("خطای ایندکس: " + (err instanceof Error ? err.message : String(err)));
      setStatusTone("error");
    } finally {
      setIndexing(false);
    }
  }

  async function onAsk(event: FormEvent) {
    event.preventDefault();
    const q = query.trim();
    if (!q) return;

    setAsking(true);
    setStatus("در حال تولید راهنما…");
    setStatusTone("idle");
    setGuideHtml("");
    setMeta(null);

    try {
      const data = await askGuide(q, audience, workspace || undefined);
      const md = normalizeGuideMarkdown(data.guide);
      setGuideHtml(marked.parse(md) as string);
      setMeta(data);
      setStatus("راهنما آماده است");
      setStatusTone("ok");
    } catch (err) {
      setStatus("خطا: " + (err instanceof Error ? err.message : String(err)));
      setStatusTone("error");
    } finally {
      setAsking(false);
    }
  }

  const stats = {
    routes: lastIndex?.routes ?? indexInfo?.routes ?? "—",
    forms: lastIndex?.forms ?? indexInfo?.forms ?? "—",
    apis: lastIndex?.api_endpoints ?? indexInfo?.api_endpoints ?? "—",
    edges: lastIndex?.edges ?? indexInfo?.edges ?? "—",
  };

  return (
    <>
      {/*
        THESIS: Code2Guide reads as a FIDS split-console, not a chat bot — index, audience, and guide are board rows.
        OWN-WORLD: navy matte LED #0b1220, cream ink #f4f1e8, amber armed #f5c518, teal live #3dd6c6; Barlow Condensed codes + Vazirmatn Persian; 1px split-flap hairlines.
        STORY: Operator arms index, picks destination audience, files a question at the gate, reads the guide as the selected flight detail.
        FIRST VIEWPORT: top LED strip; left rail destinations+workspace+index; right stage ask gate + guide pane (comp B).
        FORM: Airport FIDS split console — grounded #6 of seed bc539dcb; approved .impeccable/mocks/comp-b-split-console.png
        FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, and DESIGN.md
      */}
      <div className="app">
        <header className="strip">
          <div className="brand">
            <div className="brand-mark">Code2Guide</div>
            <div className="brand-sub">تابلوی راهنمای تجربه کاربری از روی کد</div>
          </div>
          <div className="leds" aria-label="وضعیت سامانه">
            <Led label="Index" state={indexLed} />
            <Led label="Audience" state={audienceLed} />
            <Led label="Ask" state={askLed} />
          </div>
        </header>

        <div className="console">
          <aside className="rail" aria-label="کنترل‌های اپراتور">
            <div className="panel-head">
              <span>Departures</span>
              <span>DST / IDX</span>
            </div>

            <div className="destinations" role="group" aria-label="مخاطب راهنما">
              <button
                type="button"
                className="dest"
                aria-pressed={audience === "end_user"}
                onClick={() => setAudience("end_user")}
              >
                <span className="dest-code">USR</span>
                <span className="dest-label">کاربر نهایی — بدون جزئیات فنی</span>
              </button>
              <button
                type="button"
                className="dest"
                aria-pressed={audience === "technical"}
                onClick={() => setAudience("technical")}
              >
                <span className="dest-code">TEC</span>
                <span className="dest-label">فنی / پشتیبانی — مسیر و فرم</span>
              </button>
            </div>

            <div className="rail-body">
              <div className="flap">
                <label className="flap-label" htmlFor="workspace">
                  Workspace
                </label>
                <input
                  id="workspace"
                  value={workspace}
                  onChange={(e) => setWorkspace(e.target.value)}
                  placeholder="خالی = مسیر پیش‌فرض سرور"
                  autoComplete="off"
                  spellCheck={false}
                />
              </div>

              <div className="actions">
                <button
                  type="button"
                  className="btn btn-teal"
                  onClick={() => void onIndex()}
                  disabled={indexing || asking}
                >
                  {indexing ? "Indexing…" : "Index now"}
                </button>
                <button
                  type="button"
                  className="btn"
                  onClick={() => void refreshStatus()}
                  disabled={indexing}
                >
                  Refresh
                </button>
              </div>
            </div>

            <div className="stats" aria-label="آمار ایندکس">
              <div className="stat">
                <div className="stat-k">Routes</div>
                <div className="stat-v">{stats.routes}</div>
              </div>
              <div className="stat">
                <div className="stat-k">Forms</div>
                <div className="stat-v">{stats.forms}</div>
              </div>
              <div className="stat">
                <div className="stat-k">APIs</div>
                <div className="stat-v">{stats.apis}</div>
              </div>
              <div className="stat">
                <div className="stat-k">Edges</div>
                <div className="stat-v">{stats.edges}</div>
              </div>
            </div>
          </aside>

          <main className="stage">
            <div className="panel-head">
              <span>Selected flight</span>
              <span>{audience === "end_user" ? "USR · GUIDE" : "TEC · GUIDE"}</span>
            </div>

            <form className="gate" onSubmit={onAsk}>
              <div className="gate-row">
                <label className="flap-label" htmlFor="query">
                  Question
                </label>
                <textarea
                  id="query"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  required
                  placeholder={
                    audience === "end_user"
                      ? "مثلاً: چطور یک مناقصه جدید ثبت کنم؟"
                      : "مثلاً: جریان ثبت مناقصه از فرم تا API چیست؟"
                  }
                />
                <div className="gate-actions">
                  <p
                    className="status-line"
                    data-tone={statusTone === "idle" ? undefined : statusTone}
                    role="status"
                    aria-live="polite"
                  >
                    {status}
                  </p>
                  <button type="submit" className="btn btn-primary" disabled={asking || indexing}>
                    {asking ? "Boarding…" : "Generate guide"}
                  </button>
                </div>
              </div>
            </form>

            {meta && (
              <div className="meta" aria-label="خلاصه پاسخ">
                {meta.routes_found != null && (
                  <span className="chip">Routes {meta.routes_found}</span>
                )}
                {meta.forms_found != null && (
                  <span className="chip">Forms {meta.forms_found}</span>
                )}
                {Array.isArray(meta.breadcrumbs) && meta.breadcrumbs.length > 0 && (
                  <span className="chip chip-amber">{meta.breadcrumbs.join(" › ")}</span>
                )}
              </div>
            )}

            <div className="guide-wrap">
              {asking ? (
                <div className="skeleton" aria-hidden="true">
                  <div className="skel-line" />
                  <div className="skel-line" />
                  <div className="skel-line" />
                  <div className="skel-line" />
                </div>
              ) : (
                <article
                  className="guide"
                  data-empty={emptyCopy}
                  aria-live="polite"
                  dangerouslySetInnerHTML={guideHtml ? { __html: guideHtml } : undefined}
                />
              )}
            </div>
          </main>
        </div>
      </div>
    </>
  );
}
