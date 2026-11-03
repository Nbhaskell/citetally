import type { EntryLine } from "../api/client";

const blank = (text: string | null | undefined): boolean => text === null || text === undefined || text.trim() === "";

/**
 * Lines with a unit price but no quantity. No check fires on them (line arithmetic skips a line
 * without a quantity), and the reading often drops a quantity the page prints. A line with neither
 * (a flat fee) is ordinary and is left alone.
 */
export function linesWithoutQuantity(lines: readonly EntryLine[]): EntryLine[] {
  return lines.filter((line) => blank(line.quantity) && !blank(line.unit_price));
}
