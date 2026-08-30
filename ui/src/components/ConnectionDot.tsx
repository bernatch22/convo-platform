/* Is the control plane answering? One dot, probed every few seconds, never lies. */

import { useEffect, useState } from "react";

import { probe } from "../lib/api";

const INTERVAL_MS = 6000;

type Reading = { up: boolean; ms: number } | null;

export function ConnectionDot() {
  const [reading, setReading] = useState<Reading>(null);

  useEffect(() => {
    let alive = true;
    const take = async () => {
      const next = await probe();
      if (alive) setReading(next);
    };
    void take();
    const timer = window.setInterval(() => void take(), INTERVAL_MS);
    return () => {
      alive = false;
      window.clearInterval(timer);
    };
  }, []);

  const state = reading === null ? "" : reading.up ? " probe--up" : " probe--down";
  const label = reading === null ? "probing" : reading.up ? `${reading.ms}ms` : "offline";

  return (
    <span className={`probe${state}`} title="GET /tenants">
      <span className="probe__dot" aria-hidden />
      <span>{label}</span>
    </span>
  );
}
