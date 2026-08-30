/* An empty screen that tells the truth: what is missing, which milestone fills it, how to check.
 *
 * No lorem ipsum and no fake rows: an operator who cannot tell "nothing
 * happened yet" from "the feature was never built" has been lied to by the UI.
 */

import type { ReactNode } from "react";

interface EmptyStateProps {
  title: string;
  children: ReactNode;
  milestone?: string;
  card?: string;
  command?: string;
}

export function EmptyState({ title, children, milestone, card, command }: EmptyStateProps) {
  return (
    <div className="empty">
      <div className="empty__rule" aria-hidden />
      <h2 className="empty__title">{title}</h2>
      <div className="empty__body">{children}</div>

      {(milestone || card) && (
        <div className="empty__meta">
          {milestone && <span className="badge badge--accent">{milestone}</span>}
          {card && <span className="badge badge--muted">card {card}</span>}
        </div>
      )}

      {command && <code className="empty__cmd">{command}</code>}
    </div>
  );
}
