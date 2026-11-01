/** How long ago, in the shortest honest words: "just now", "5 min", "3 h", "2 d". */
export function age(iso: string, now: Date = new Date()): string {
  const seconds = Math.max(0, Math.floor((now.getTime() - new Date(iso).getTime()) / 1000));
  if (seconds < 45) return "just now";
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes} min`;
  const hours = Math.round(minutes / 60);
  if (hours < 48) return `${hours} h`;
  return `${Math.round(hours / 24)} d`;
}

/** A calendar date printed on a document ("2026-03-14") as "14 Mar 2026". No time zone shifts. */
export function shortDate(iso: string | null | undefined): string {
  if (!iso || !/^\d{4}-\d{2}-\d{2}$/.test(iso)) return "";
  return new Intl.DateTimeFormat("en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  }).format(new Date(`${iso}T00:00:00Z`));
}

export function secondsSince(iso: string, now: Date = new Date()): number {
  return Math.max(0, (now.getTime() - new Date(iso).getTime()) / 1000);
}
