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

export type Period = "month" | "30d" | "90d" | "year" | "all";

function isoDay(date: Date): string {
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${date.getFullYear()}-${month}-${day}`;
}

/** The first and last day (as "2026-03-14") a period covers, counting back from today. */
export function periodRange(period: Period, today: Date = new Date()): { from: string | null; to: string | null } {
  const to = isoDay(today);
  switch (period) {
    case "month":
      return { from: isoDay(new Date(today.getFullYear(), today.getMonth(), 1)), to };
    case "30d":
      return { from: isoDay(new Date(today.getFullYear(), today.getMonth(), today.getDate() - 29)), to };
    case "90d":
      return { from: isoDay(new Date(today.getFullYear(), today.getMonth(), today.getDate() - 89)), to };
    case "year":
      return { from: isoDay(new Date(today.getFullYear(), 0, 1)), to };
    default:
      return { from: null, to: null };
  }
}

/** Seconds in the plainest words: "45 s", "1 min 30 s", "12 min". */
export function duration(seconds: number): string {
  if (seconds < 60) return `${seconds} s`;
  const minutes = Math.floor(seconds / 60);
  const rest = seconds % 60;
  if (minutes >= 10 || rest === 0) return `${minutes} min`;
  return `${minutes} min ${rest} s`;
}
