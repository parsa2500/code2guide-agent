import BackButton, { HubLink } from "../components/BackButton";

type Props = {
  title: string;
  code: string;
  blurb?: string;
};

export default function PlaceholderPage({ title, code, blurb }: Props) {
  return (
    <div className="app shell-page">
      <header className="strip">
        <div className="brand">
          <div className="brand-mark">Code2Guide</div>
          <div className="brand-sub">{title}</div>
        </div>
        <div className="leds">
          <BackButton to="/" />
          <HubLink />
        </div>
      </header>
      <main className="shell-main">
        <div className="panel-head">
          <span>{code}</span>
          <span>Coming soon</span>
        </div>
        <div className="placeholder-panel">
          <p className="placeholder-code">{code}</p>
          <h1>{title}</h1>
          <p>{blurb || "این بخش فعلاً فقط فرانت placeholder است و به بک وصل نشده."}</p>
          <BackButton to="/" label="بازگشت به هاب" />
        </div>
      </main>
    </div>
  );
}
