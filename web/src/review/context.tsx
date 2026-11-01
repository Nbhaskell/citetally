import { createContext, useContext } from "react";

import type { CategoryOut, EntryOut, EntryPatch, Evidence } from "../api/client";
import type { FieldKey } from "./fields";

/** What the parts of the Review screen share: the entry, which value is in focus, and saving. */
export interface ReviewApi {
  entry: EntryOut;
  currency: string;
  /** Only a document waiting for review can be edited. */
  editable: boolean;
  evidence: ReadonlyMap<FieldKey, Evidence>;
  categories: readonly CategoryOut[];
  activeKey: FieldKey | null;
  setActive: (key: FieldKey | null) => void;
  /** Highlight the value on the page and move keyboard focus to its input. */
  focusKey: (key: FieldKey) => void;
  /** Highlight the value on the page (and show the page, on a phone) without leaving the form. */
  showKey: (key: FieldKey) => void;
  /** Save a change; resolves true when it was saved. The checks are run again by the server. */
  save: (patch: EntryPatch) => Promise<boolean>;
  openVendorPicker: () => void;
}

export const ReviewContext = createContext<ReviewApi | null>(null);

export function useReview(): ReviewApi {
  const value = useContext(ReviewContext);
  if (!value) throw new Error("useReview needs a Review screen around it");
  return value;
}
