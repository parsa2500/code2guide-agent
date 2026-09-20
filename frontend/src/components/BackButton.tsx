import { Link } from "react-router-dom";

type Props = {
  /** Parent route to return to */
  to?: string;
  label?: string;
};

/** Explicit back link to the parent board / previous shell page. */
export default function BackButton({ to = "/", label = "بازگشت" }: Props) {
  return (
    <Link to={to} className="btn btn-nav">
      ← {label}
    </Link>
  );
}

export function HubLink() {
  return (
    <Link to="/" className="btn btn-nav">
      هاب
    </Link>
  );
}
