# UI/UX Design Brief: Citetally

Version 0.1. Screens, behavior, copy and accessibility. Statuses and check codes are from `BACKEND_SCHEMA.md`; flows are in `APP_FLOW.md`. Visual style is deliberately left open (section 3) so the build can use the `frontend-design` skill and the `ai-ui-patterns` skill.

## 1. Who it is for and what the screen must do

A bookkeeper or owner clearing a pile of invoices and receipts, often between other jobs. They want to see at a glance what needs attention, fix a wrong number in seconds, and trust that nothing is approved by accident. The core job of the UI is **fast, confident review**: every value sits next to the place on the page it came from, and every problem is explained in plain words.

Design goals:
1. **Evidence beside every value.** Click a value and see where it is on the page; click the page and see which value it is.
2. **Problems are shown, never hidden.** A document with failed checks is a normal state, not an error.
3. **Approval is deliberate.** Nothing is approved, exported or sent by a side effect. The one-way steps (approve, export) are clear.
4. **Keyboard first on desktop, usable on a phone.** Reviewing many documents is repetitive; uploading a photo from a phone should take two taps.
5. **Honest about being a demo.** Synthetic data is labelled; hosted mode is loudly labelled.

## 2. Screens

### 2.1 Inbox (home)

- **Upload area** at the top: drag and drop, "Choose files", and "Take a photo" on devices with a camera. Accepts PDF, PNG, JPEG. Short guidance underneath: "Lay the page flat, fill the frame, good light, no glare."
- **Status summary** as clickable chips with counts: Needs review, Approved, Rejected, Exported, Failed, Duplicates. Needs review is selected by default.
- **Queue table**: file name, vendor (or "Unknown vendor"), date, total, a compact check summary (for example "2 blocking, 1 warning" or "All checks passed"), status, and age. Rows still processing show the current step in words and a quiet progress indicator.
- **Filters**: text search (vendor, invoice number), status, check code, batch (upload session).
- **Sort**: oldest first by default for review; a "blocking checks first" option.
- Row actions: open, retry (failed), and nothing destructive. Bulk approve does not exist in v1: each entry is approved after being seen.
- Empty state: "Nothing here yet. Drop in an invoice or receipt to begin." plus a "Load demo documents" button when the data is synthetic.

### 2.2 Review (the main screen)

Two panes side by side on desktop, stacked tabs on a phone.

**Left: the page.** The rendered page image with a box over each located value. Zoom and pan, page selector for multi-page files, "Fit width" and "Actual size". Boxes use a color plus an outline style (never color alone): solid for found, dashed for "not found on the page" fields shown in the margin list. Clicking a box focuses its field on the right; focusing a field scrolls and highlights its box.

**Right: the entry.**
- **Header block:** document type (invoice, receipt, credit note), vendor (with match state: matched, suggested, unknown), invoice number, entry date, due date, PO number, currency, category.
- **Line items table:** description, quantity, unit price, amount. Each row shows its arithmetic in words under or beside it: "10 × $4.50 = $45.00" with a tick when it matches the printed amount, or "Printed $54.00" in a warning style when it does not. Rows are editable. Add and remove line are available.
- **Totals block:** subtotal, tax, shipping, discount, total as printed, next to "Calculated" values so a difference is obvious: "Printed total $236.50, calculated $235.50, difference $1.00".
- **Checks panel:** grouped as "Must be resolved before approving" (blocking) and "Worth a look" (non-blocking). Each item: a plain-language title, a one-line explanation with the actual numbers, and an action ("Show on page", "Fix value", "Pick vendor", "Override with reason"). Passed checks are collapsed into one line ("9 checks passed").
- **Action bar** (sticky at the bottom): **Approve entry** (disabled with a visible reason while blocking checks are unresolved), **Reject…**, **Mark as duplicate of…**, **Reprocess…**, and, for approved or rejected entries, **Reopen**. After a decision, the next item opens automatically, with a brief toast and an Undo that is available until the next navigation (Undo is a reopen).
- **History** drawer: reads, extractions, edits (old value → new value), checks run, decisions, with times. No document text beyond the field values the reviewer saw.

Dialogs:
- **Override:** names the check, shows its detail, requires a reason of at least a short sentence, and says "This will be recorded."
- **Reject:** required reason with quick choices (Not an invoice, Unreadable, Multiple invoices in one file, Other).
- **Mark as duplicate:** search the other documents by vendor, number or total; shows both side by side before confirming.
- **Vendor picker:** search existing vendors; "Create vendor" prefilled with the printed name; "Add the printed name as an alias of…" for fuzzy matches; shows the fuzzy score as a word ("Probably the same: Brightway Supply Co.").

### 2.3 Vendors

Table of vendors with default category, number of entries, aliases, last invoice date. Add alias, change default category, merge two vendors (with a preview of what will change). The merge dialog is explicit about the consequence.

### 2.4 Exports

- "Ready to export: N approved entries" with the total amount and date range.
- Profile choice: "One row per line item" or "One row per entry", with a short sample of the first rows before exporting.
- Checkbox "Include entries I've already exported", unticked, with a warning when ticked: "These may already be in your accounting software. Importing them again can create duplicates."
- Export button creates the file and offers a download. History list below: date, profile, entry count, file hash, download again.
- Copy under the button: "Citetally never sends data anywhere. You import this file into your accounting software yourself."

### 2.5 Insights

Small, honest summaries: spending by category and by vendor for a chosen period, entries waiting by age, how many documents needed edits (and which fields were most often edited), the checks that fire most often, median review time. Charts follow the `dataviz` skill. Every chart has a text equivalent (a table) available. Do not invent forecasts.

### 2.6 Settings

Read-only status first: model provider and model name, OCR engine, database health, hosted mode flag, synthetic-data flag. Editable: default currency, locale (date and number order), duplicate window, outlier ratio, low-read threshold. A "Run checks on sample documents" self-test button. Hosted-mode settings appear only when allowed by the environment, with the provider data-handling warning.

## 3. Visual direction (left open on purpose)

Do not default to a generic dashboard template. Pick one clear direction before building and record it in `docs/DECISIONS.md`. Constraints that hold whatever the style:

- **Tone:** a calm bookkeeper's desk. Quiet, precise, trustworthy. Not playful, not "AI sparkle".
- **Figures:** tabular (monospaced-width) numerals, right-aligned, same decimal places in a column, a consistent currency symbol position. Negative amounts and credit notes are visibly different (a minus sign and a label, not only color).
- **Color is never the only signal.** Every status and check state also has an icon and a word.
- **Density:** the review screen is allowed to be dense; the inbox is not. Comfortable row height, clear hierarchy.
- **Page image is the hero** on the Review screen; the form is secondary but never cramped.
- **Motion:** minimal. A highlight pulse when a box is focused; respect reduced-motion settings.
- **Dark mode:** supported if it does not cost the page image's legibility; light mode first.
- Avoid: stock gradients, purple-blue "AI" palette, emoji as icons, decorative illustrations, fake loading theatrics.

## 4. Copy

Plain words. No jargon like "grounding", "extraction", or "token" in the UI.

| Code | Title shown | Explanation pattern |
|---|---|---|
| `REQUIRED_FIELDS` | Something is missing | "Invoice number is missing. Invoices need a vendor, an invoice number, a date, a total and a category." |
| `VALUE_IN_DOCUMENT` | A value isn't on the page | "We couldn't find '$1,240.00' on the page. It may have been misread. Check it against the page." |
| `LINE_MATH` | A line doesn't add up | "Line 3: 10 × $4.50 is $45.00, but the page says $54.00." |
| `SUBTOTAL_MATCH` | Lines don't match the subtotal | "The lines add up to $212.00. The page says the subtotal is $215.00." |
| `TAX_MATCH` | Tax looks off | "8% of $212.00 is $16.96. The page says $19.96." |
| `TOTAL_MATCH` | Total doesn't add up | "Subtotal + tax + shipping − discount is $235.50. The page says $236.50." |
| `DUPLICATE_SUSPECT` | Might be a duplicate | "Same vendor and invoice number as INV-2041 entered on May 3." (link to the other entry) |
| `UNKNOWN_VENDOR` | New vendor | "'Brightway Supply' isn't in your vendor list. Pick an existing vendor or add it." |
| `AMOUNT_OUTLIER` | Unusually large (or small) | "This is 4.2 times this vendor's usual invoice." |
| `DATE_SANITY` | A date looks wrong | "The invoice date is in the future." / "The due date is before the invoice date." |
| `CURRENCY_CHECK` | Different currency | "This invoice is in EUR. Your default is USD." |
| `LOW_READ_QUALITY` | Hard to read | "This scan is blurry, so check every number against the page." |
| `AMBIGUOUS_FORMAT` | Date or number could be read two ways | "03/04/2026 could be March 4 or April 3. We read it as March 4." |
| `SUSPICIOUS_TEXT` | The page contains instructions | "The page includes text addressed to a reader or system. It was ignored. Review as usual." |

Buttons use verbs and objects: "Approve entry", "Reject document", "Export approved entries". Error messages say what happened and what to do next. Overrides: "I've checked this and it's correct because…".

## 5. Behavior details

- **Keyboard (desktop Review):** `j` / `k` next and previous item; `Enter` open; `a` approve (when allowed); `r` reject dialog; `e` focus the first editable field; `Tab` moves through fields in reading order; `g` then `p` toggles page focus; `?` shows shortcuts. Shortcuts do nothing while typing in a field.
- **Edit feedback:** saving a field shows the checks updating within a moment; changed checks briefly highlight.
- **Autosave:** edits save on blur. A small "Saved" indicator; a visible failure state if saving fails.
- **Disabled approve:** the button stays visible and explains why on hover and focus: "2 checks must be resolved first".
- **Processing:** a document processing shows steps in plain words. If a step takes unusually long, say so ("Still working. The model is slow right now.").
- **Hosted mode:** a persistent top banner: "Hosted model mode: page content is sent to <provider>." It cannot be dismissed.
- **Synthetic footer:** "Demo data. All vendors, invoices and amounts are invented." on every screen while `synthetic_data` is true.
- **Safe rendering:** all document and model text is rendered as plain text. Never as HTML. Long strings wrap or truncate with a tooltip; they never break the layout.
- **Camera upload:** the app is bound to `127.0.0.1`, so "Take a photo" uses the camera of the device the browser runs on (a laptop webcam, say). Phone photos are tested by transferring the image file and uploading it. Do not add network exposure to make phone capture work; that needs authentication first.

## 6. Accessibility

- Meet WCAG 2.2 AA: contrast, focus visibility, target size (at least 24 px, aim for 44 px on touch).
- Every interactive element is reachable and operable by keyboard, with a logical order and a visible focus ring.
- The page image has a text alternative: the page text as read, available in a collapsible "Text as read" panel.
- Evidence boxes are also exposed as a list ("Total: found on page 1") so screen reader users do not depend on the image.
- Status and check states have text and icons, not only color.
- Announce changes (checks updated, saved, decision recorded) with polite live regions.
- Reduced motion respected. Zoom to 200% without loss of function.

## 7. Responsive behavior

- 1280 px and wider: two panes, 55% page and 45% form.
- 768 to 1279 px: two panes with a collapsible checks drawer.
- Below 768 px (down to 360 px): tabs "Page", "Details", "Checks"; sticky action bar; tables become stacked cards; no horizontal page scroll.

## 8. States checklist (every screen)

Empty, loading, partial (some documents still processing), error (with retry), offline model, success, and permission-style blocked states (approve disabled, reopen not allowed after export). Each has designed copy, not a blank panel.

## 9. Components to build once and reuse

Status chip, check row, money cell, evidence box, field with evidence link, line-item row with arithmetic, vendor picker, reason dialog, banner, toast with undo, shortcut help, empty state, skeleton row.

## 10. Open design questions

1. Does the review screen work better with the page on the left or on the right for left-to-right readers who read the form first? Try left first; test with five synthetic documents.
2. How should multi-page documents be shown: a vertical scroll of all pages, or one page at a time? Start with one page at a time plus a thumbnail strip.
3. Should the line-item table show the printed value and the calculated value in two columns, or inline? Prototype both and keep the one that is faster to scan.
