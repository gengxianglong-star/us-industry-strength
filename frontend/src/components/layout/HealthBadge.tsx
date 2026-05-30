import { useEffect, useRef } from "react";
import { loadHealthBadge } from "../../lib/api";

export function HealthBadge() {
  const ref = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    loadHealthBadge(ref.current).catch(() => {});
  }, []);

  return (
    <span ref={ref} className="health-badge" role="status" aria-live="polite">
      Checking…
    </span>
  );
}
