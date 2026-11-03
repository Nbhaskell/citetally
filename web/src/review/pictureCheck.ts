import type { CheckOut, DocumentDetail } from "../api/client";

/** The start of the recorded reason when a reviewer confirms values against the page picture. */
export const PICTURE_CHECK_REASON = "Checked against the picture";

export interface Unlocated {
  field: string;
  line: number | null;
  printed: string;
}

/** The values the model returned that the page words could not place (from the check's detail). */
export function unlocatedValues(check: CheckOut): Unlocated[] {
  const rows = (check.detail as { not_found?: unknown }).not_found;
  if (!Array.isArray(rows)) return [];
  return rows.map((row: Record<string, unknown>) => ({
    field: String(row.field),
    line: typeof row.line === "number" ? row.line : null,
    printed: String(row.printed ?? ""),
  }));
}

/**
 * Whether this failed check can be confirmed against the picture: it is the "value is not on the
 * page" check, the values were read from the page picture, and a page was read by OCR (so there is
 * a picture whose words could be wrong or missing). Nothing else gets the shortcut.
 */
export function canCheckAgainstPicture(check: CheckOut, detail: DocumentDetail): boolean {
  return (
    check.check_code === "VALUE_IN_DOCUMENT" &&
    check.blocking &&
    !check.passed &&
    !check.overridden &&
    detail.extraction?.extract_mode === "text_and_image" &&
    detail.pages.some((page) => page.read_method === "ocr") &&
    unlocatedValues(check).length > 0
  );
}

/** The reason stored with the override. Counts only: no document text goes into it. */
export function pictureCheckReason(count: number): string {
  return `${PICTURE_CHECK_REASON}: ${count} ${count === 1 ? "value" : "values"} the page words did not place.`;
}
