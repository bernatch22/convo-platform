/* The console's URL vocabulary, in one place.
 *
 * Every working screen lives under a project: `/t/<tenant>/<project>` is Talk,
 * and each other section hangs one segment below it. That shape is deliberate
 * — the URL carries the whole truth about where you are standing, so the rail
 * can highlight the tenant, the project AND the section without keeping a
 * single byte of state.
 */

/** The sections a project has, in the order the rail lists them. Talk is the project's root.
 *
 * Board sits beside Sessions because they are the same evidence read two ways:
 * Sessions is every conversation, Board is what those conversations DID to the
 * business. Both are computed off the one append-only log.
 */
export const SECTIONS = ["talk", "sessions", "board", "pipeline"] as const;

export type Section = (typeof SECTIONS)[number];

/** Where one section of one project lives. */
export function sectionPath(tenant: string, project: string, section: Section): string {
  const base = `/t/${encodeURIComponent(tenant)}/${encodeURIComponent(project)}`;
  return section === "talk" ? base : `${base}/${section}`;
}

/** Which section a pathname stands in, or null when it is not a project screen at all. */
export function sectionOf(pathname: string): Section | null {
  const parts = pathname.split("/").filter(Boolean);
  if (parts[0] !== "t" || parts.length < 3) return null;

  const section = parts[3];
  if (section === undefined) return "talk";
  return SECTIONS.includes(section as Section) ? (section as Section) : null;
}
