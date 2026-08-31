/* Theme is a data-theme attribute on <html>: "dark" (default) or "light".
 * The pre-paint script in index.html sets it before React mounts so there is
 * no flash; this module is how the running app reads and flips it. The stored
 * key is shared verbatim with that inline script — change one, change both.
 */

export type Theme = "light" | "dark";

const STORAGE_KEY = "convo-theme";

/** The theme currently painted on <html> — "dark" unless the attribute says light. */
export function currentTheme(): Theme {
  return document.documentElement.dataset.theme === "light" ? "light" : "dark";
}

/** Flip the theme, paint it, and remember the choice. Returns the new theme. */
export function toggleTheme(): Theme {
  const next: Theme = currentTheme() === "light" ? "dark" : "light";
  applyTheme(next);
  persist(next);
  return next;
}

/** Paint a theme without persisting — used by the pre-paint path and toggle. */
export function applyTheme(theme: Theme): void {
  document.documentElement.dataset.theme = theme;
}

/** The choice the operator made last, or null if they never chose. */
export function storedTheme(): Theme | null {
  try {
    const value = localStorage.getItem(STORAGE_KEY);
    return value === "light" || value === "dark" ? value : null;
  } catch {
    return null;
  }
}

/** What the OS asks for; the fallback when nothing was chosen. */
export function systemTheme(): Theme {
  return window.matchMedia?.("(prefers-color-scheme: light)").matches ? "light" : "dark";
}

function persist(theme: Theme): void {
  try {
    localStorage.setItem(STORAGE_KEY, theme);
  } catch {
    /* Private mode denies storage: honour the choice for this session only. */
  }
}
