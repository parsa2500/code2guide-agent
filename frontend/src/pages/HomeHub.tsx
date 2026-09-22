import { Link } from "react-router-dom";

const tiles = [
  {
    to: "/workspaces",
    code: "WKS",
    title: "انتخاب workspace",
    desc: "مدیریت و ورود به workspaceها",
  },
  {
    to: "/agents",
    code: "AGT",
    title: "ایجنت‌ها",
    desc: "رجیستری سراسری ایجنت‌ها",
  },
  {
    to: "/brain-settings",
    code: "BRN",
    title: "تنظیمات مغز",
    desc: "Qdrant و مدل embedding",
  },
  {
    to: "/api-mcp",
    code: "API",
    title: "API & MCP",
    desc: "قراردادها و اتصال MCP — به‌زودی",
  },
  {
    to: "/pipeline",
    code: "PIP",
    title: "Pipeline",
    desc: "جریان ایندکس و پردازش — به‌زودی",
  },
  {
    to: "/guide",
    code: "DOC",
    title: "راهنما",
    desc: "راهنمای محصول — به‌زودی",
  },
  {
    to: "/ask",
    code: "ASK",
    title: "کنسول Ask فعلی",
    desc: "ورود به صفحهٔ ask/index فعلی",
    accent: true,
  },
] as const;

export default function HomeHub() {
  return (
    <div className="app shell-page">
      <header className="strip">
        <div className="brand">
          <div className="brand-mark">Code2Guide</div>
          <div className="brand-sub">هاب عملیات</div>
        </div>
        <div className="leds">
          <span className="led" data-state="ok">
            <span className="led-dot" aria-hidden="true" />
            Hub
          </span>
        </div>
      </header>

      <main className="shell-main">
        <div className="panel-head">
          <span>Destinations</span>
          <span>Select board</span>
        </div>
        <div className="hub-grid">
          {tiles.map((tile) => (
            <Link
              key={tile.to}
              to={tile.to}
              className={`hub-tile${"accent" in tile && tile.accent ? " hub-tile-accent" : ""}`}
            >
              <span className="hub-code">{tile.code}</span>
              <span className="hub-title">{tile.title}</span>
              <span className="hub-desc">{tile.desc}</span>
            </Link>
          ))}
        </div>
      </main>
    </div>
  );
}
