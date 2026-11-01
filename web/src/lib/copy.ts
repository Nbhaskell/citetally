// Words the screens use. Plain language: no "grounding", "extraction" or "token" (UI brief section 4).

import type { CheckCode, DocumentStatus } from "../api/client";

export type Tone = "ok" | "warn" | "block" | "info" | "quiet";

export const STATUS: Record<DocumentStatus, { label: string; tone: Tone; icon: IconName }> = {
  received: { label: "Waiting", tone: "quiet", icon: "clock" },
  read: { label: "Reading", tone: "quiet", icon: "clock" },
  extracted: { label: "Checking", tone: "quiet", icon: "clock" },
  needs_review: { label: "Needs review", tone: "info", icon: "eye" },
  approved: { label: "Approved", tone: "ok", icon: "check" },
  rejected: { label: "Rejected", tone: "quiet", icon: "close" },
  exported: { label: "Exported", tone: "ok", icon: "check" },
  failed: { label: "Failed", tone: "block", icon: "alert" },
  duplicate: { label: "Duplicate", tone: "quiet", icon: "copy" },
};

export type IconName =
  | "clock"
  | "eye"
  | "check"
  | "close"
  | "alert"
  | "copy"
  | "block"
  | "info"
  | "upload"
  | "camera"
  | "file"
  | "search"
  | "retry"
  | "chevron";

/** What a document that is still being processed is doing, in words. */
export const PROCESSING_STEP: Partial<Record<DocumentStatus, string>> = {
  received: "Reading the pages",
  read: "Finding the values",
  extracted: "Checking the numbers",
};

export const PROCESSING: readonly DocumentStatus[] = ["received", "read", "extracted"];

export const CHECK_TITLE: Record<CheckCode, string> = {
  REQUIRED_FIELDS: "Something is missing",
  VALUE_IN_DOCUMENT: "A value isn't on the page",
  LINE_MATH: "A line doesn't add up",
  SUBTOTAL_MATCH: "Lines don't match the subtotal",
  TAX_MATCH: "Tax looks off",
  TOTAL_MATCH: "Total doesn't add up",
  DUPLICATE_SUSPECT: "Might be a duplicate",
  UNKNOWN_VENDOR: "New vendor",
  AMOUNT_OUTLIER: "Unusually large (or small)",
  DATE_SANITY: "A date looks wrong",
  CURRENCY_CHECK: "Different currency",
  LOW_READ_QUALITY: "Hard to read",
  AMBIGUOUS_FORMAT: "Date or number could be read two ways",
  SUSPICIOUS_TEXT: "The page contains instructions",
};

/** How a check reads when it passed. */
export const PASSED_TITLE: Record<CheckCode, string> = {
  REQUIRED_FIELDS: "Nothing is missing",
  VALUE_IN_DOCUMENT: "Every value is on the page",
  LINE_MATH: "Lines add up",
  SUBTOTAL_MATCH: "Lines match the subtotal",
  TAX_MATCH: "Tax is consistent",
  TOTAL_MATCH: "Total adds up",
  DUPLICATE_SUSPECT: "Not a duplicate of anything else",
  UNKNOWN_VENDOR: "Vendor is known",
  AMOUNT_OUTLIER: "Amount is in the usual range",
  DATE_SANITY: "Dates look right",
  CURRENCY_CHECK: "Usual currency",
  LOW_READ_QUALITY: "Easy to read",
  AMBIGUOUS_FORMAT: "Dates and numbers read one way",
  SUSPICIOUS_TEXT: "No instructions on the page",
};

export const NOT_FOUND_ADVICE = "Start the API with: python -m citetally";

/** Which stage a failed document should be sent back to, or null when retrying cannot help. */
export function retryStage(failureStage: string | null | undefined): "read" | "extract" | null {
  switch (failureStage) {
    case "read":
      return "read";
    case "extract":
    case "ground":
    case "match":
    case "check":
      return "extract";
    default:
      return null; // a file that could not be accepted stays refused
  }
}
