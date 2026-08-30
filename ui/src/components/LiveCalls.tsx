/* What is ringing right now — a web session and an inbound phone call, in the same strip.
 *
 * An inbound call never passed through /token, so the SFU is the only place it
 * exists before its log is worth reading. Three answers are three different
 * sentences and the strip must never blur them: calls, no calls, or the SFU
 * could not be asked.
 */

import { useEffect, useState } from "react";

import { ApiError, listLiveCalls, type LiveCall } from "../lib/api";

const INTERVAL_MS = 5000;

type Reading =
  | { state: "loading" }
  | { state: "calls"; calls: LiveCall[] }
  | { state: "sfu-down"; detail: string }
  | { state: "unavailable"; detail: string };

export function LiveCalls() {
  const reading = useLiveCalls();

  return (
    <section className="section">
      <h2 className="section__title">Live now</h2>
      {render(reading)}
    </section>
  );
}

function render(reading: Reading) {
  switch (reading.state) {
    case "loading":
      return <p className="note">asking the SFU…</p>;
    case "sfu-down":
      return <p className="note note--warn">the SFU could not be asked — {reading.detail}</p>;
    case "unavailable":
      return <p className="note">GET /live-calls is not served by this build</p>;
    case "calls":
      return reading.calls.length === 0 ? (
        <p className="note">no call in progress</p>
      ) : (
        <CallTable calls={reading.calls} />
      );
  }
}

function CallTable({ calls }: { calls: LiveCall[] }) {
  return (
    <div className="table-wrap">
      <table className="table">
        <thead>
          <tr>
            <th>room</th>
            <th>from</th>
            <th>routed to</th>
            <th className="num">in room</th>
            <th>session</th>
          </tr>
        </thead>
        <tbody>
          {calls.map((call) => (
            <tr key={call.sid}>
              <td className="id">{call.room}</td>
              <td className="mono">{call.phone ?? "web"}</td>
              <td className="mono">
                {call.tenant && call.project ? `${call.tenant} / ${call.project}` : "—"}
              </td>
              <td className="num">{call.participants}</td>
              <td className="id">{call.session_id ?? "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function useLiveCalls(): Reading {
  const [reading, setReading] = useState<Reading>({ state: "loading" });

  useEffect(() => {
    let alive = true;
    const take = async () => {
      const next = await read();
      if (alive) setReading(next);
    };
    void take();
    const timer = window.setInterval(() => void take(), INTERVAL_MS);
    return () => {
      alive = false;
      window.clearInterval(timer);
    };
  }, []);

  return reading;
}

async function read(): Promise<Reading> {
  try {
    return { state: "calls", calls: await listLiveCalls() };
  } catch (cause) {
    if (cause instanceof ApiError && cause.status === 503) {
      return { state: "sfu-down", detail: cause.detail };
    }
    return { state: "unavailable", detail: String(cause) };
  }
}
