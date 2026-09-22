import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { Link } from "react-router-dom";
import BackButton, { HubLink } from "../components/BackButton";
import type { BrainSettings } from "../api/brainSettings";
import {
  EMBEDDING_PROVIDERS,
  emptyBrainSettings,
  getBrainSettings,
  putBrainSettings,
} from "../api/brainSettings";

export default function BrainSettingsPage() {
  const [settings, setSettings] = useState<BrainSettings>(emptyBrainSettings);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [missing, setMissing] = useState(false);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      setLoading(true);
      setError(null);
      try {
        const data = await getBrainSettings();
        if (cancelled) return;
        setSettings(data);
        setMissing(!data.qdrant_url && !data.embedding_model);
      } catch (e) {
        if (cancelled) return;
        setError(e instanceof Error ? e.message : String(e));
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const providerKnown = (EMBEDDING_PROVIDERS as readonly string[]).includes(
    settings.embedding_provider,
  );

  async function onSave(e: FormEvent) {
    e.preventDefault();
    setSaving(true);
    setError(null);
    try {
      const next = await putBrainSettings(settings);
      setSettings(next);
      setMissing(false);
      setSaved(true);
      window.setTimeout(() => setSaved(false), 1500);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="app shell-page">
      <header className="strip">
        <div className="brand">
          <div className="brand-mark">Code2Guide</div>
          <div className="brand-sub">تنظیمات مغز</div>
        </div>
        <div className="leds">
          <BackButton to="/" />
          <HubLink />
          <Link to="/agents" className="btn btn-nav">
            ایجنت‌ها
          </Link>
        </div>
      </header>

      <main className="shell-main">
        <div className="panel-head">
          <span>Brain</span>
          <span>{loading ? "…" : "global config"}</span>
        </div>

        <form className="tab-stack form-grid" onSubmit={(e) => void onSave(e)}>
          {error ? (
            <p className="empty-hint" data-tone="error" role="alert">
              {error}
            </p>
          ) : null}
          {!loading && missing && !error ? (
            <p className="empty-hint">تنظیمات مغز هنوز ذخیره نشده. مقادیر را بنویسید و ذخیره کنید.</p>
          ) : null}

          <div className="flap">
            <label className="flap-label" htmlFor="qdrant-url">
              آدرس Qdrant
            </label>
            <input
              id="qdrant-url"
              value={settings.qdrant_url}
              onChange={(e) => setSettings({ ...settings, qdrant_url: e.target.value })}
              dir="ltr"
              spellCheck={false}
              placeholder="http://localhost:6333"
              disabled={loading || saving}
              required
            />
          </div>

          <div className="flap">
            <label className="flap-label" htmlFor="embedding-provider">
              ارائه‌دهنده embedding
            </label>
            <select
              id="embedding-provider"
              value={settings.embedding_provider}
              onChange={(e) => setSettings({ ...settings, embedding_provider: e.target.value })}
              disabled={loading || saving}
            >
              {!providerKnown && settings.embedding_provider ? (
                <option value={settings.embedding_provider}>{settings.embedding_provider}</option>
              ) : null}
              <option value="google">google</option>
              <option value="fastembed">fastembed</option>
              <option value="none">none</option>
            </select>
          </div>

          <div className="flap">
            <label className="flap-label" htmlFor="embedding-model">
              مدل embedding
            </label>
            <input
              id="embedding-model"
              value={settings.embedding_model}
              onChange={(e) => setSettings({ ...settings, embedding_model: e.target.value })}
              dir="ltr"
              spellCheck={false}
              placeholder="text-embedding-004"
              disabled={loading || saving}
              required
            />
            <p className="field-hint">
              ایندکس پوشهٔ هر workspace روی تب آپدیت همان workspace می‌ماند.
            </p>
          </div>

          <div className="toolbar">
            <button type="submit" className="btn btn-primary" disabled={loading || saving}>
              {saving ? "در حال ذخیره…" : "ذخیره تنظیمات مغز"}
            </button>
            {saved ? (
              <span className="status-line" data-tone="ok">
                ذخیره شد
              </span>
            ) : null}
          </div>
        </form>
      </main>
    </div>
  );
}
