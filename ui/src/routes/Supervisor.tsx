/* Supervisor — the desk: every call live on the fleet right now, in one strip.
 *
 * The strip is a readout today and nothing more. What turns a row into a seat
 * is a ticket from POST /supervise, and the grants inside that ticket are what
 * decide whether the human hears the call, whispers to the agent or takes the
 * line — never a button on this page. So the shell lands first, and the verbs
 * arrive on top of it card by card.
 */

import { LiveCalls } from "../components/LiveCalls";

export function Supervisor() {
  return (
    <div className="page">
      <header className="page__head">
        <div className="page__eyebrow">fleet</div>
        <h1 className="page__title">Supervisor</h1>
        <p className="page__lede">
          Every call in progress across every tenant, phone calls included. A supervisor enters one
          of them with a short-lived ticket from <code className="mono">POST /supervise</code>: the
          identity is always <code className="mono">sup:&lt;uid&gt;</code>, and the capability
          inside the token — not a control on this screen — is what separates listening from taking
          the line.
        </p>
      </header>

      <LiveCalls />

      <section className="section">
        <h2 className="section__title">What a ticket allows</h2>
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>capability</th>
                <th>in the room</th>
                <th>logged as</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td className="mono">listen</td>
                <td>hidden, subscribe-only — the caller is never told anybody joined</td>
                <td className="mono">supervisor.join</td>
              </tr>
              <tr>
                <td className="mono">whisper</td>
                <td>still hidden and still silent, but may send the agent text</td>
                <td className="mono">supervisor.steer</td>
              </tr>
              <tr>
                <td className="mono">takeover</td>
                <td>a real microphone, and a participant the caller can see</td>
                <td className="mono">supervisor.takeover</td>
              </tr>
            </tbody>
          </table>
        </div>
        <p className="note">
          Each verb is appended to the caller&apos;s own session log with its own{" "}
          <code className="mono">seq</code>, so one call stays one story.
        </p>
      </section>
    </div>
  );
}
