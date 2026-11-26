---
name: Cite design system
description: One calm, status-page style for Citebrief, Citedesk, Citebook, and Citetally.
colors:
  ink: "#1a1d21"
  slate: "#565b62"
  surface: "#ffffff"
  canvas: "#f3f4f6"
  border: "#e1e4e8"
  rule: "#eceef1"
  input-border: "#858b94"
  neutral-text: "#565b62"
  neutral-tint: "#f3f4f6"
  harbor-navy: "#173f6b"
  harbor-navy-deep: "#0f2f52"
  link-blue: "#0b4fa3"
  danger-text: "#8a1c1c"
  danger-tint: "#fdeeee"
  danger-line: "#efc4c4"
  danger-solid: "#b42318"
  danger-solid-deep: "#912018"
  success-text: "#1f5130"
  success-tint: "#e6f3ea"
  info-text: "#173f6b"
  info-tint: "#e6eef8"
  warning-text: "#5c3b00"
  warning-tint: "#fff5d6"
  warning-line: "#ecd48f"
typography:
  headline:
    fontFamily: "system-ui, -apple-system, Segoe UI, Roboto, sans-serif"
    fontSize: "1.75rem"
    fontWeight: 700
    lineHeight: 1.2
    letterSpacing: "-0.02em"
  title:
    fontFamily: "system-ui, -apple-system, Segoe UI, Roboto, sans-serif"
    fontSize: "1rem"
    fontWeight: 700
    lineHeight: 1.3
  body:
    fontFamily: "system-ui, -apple-system, Segoe UI, Roboto, sans-serif"
    fontSize: "0.9375rem"
    fontWeight: 400
    lineHeight: 1.55
  small:
    fontFamily: "system-ui, -apple-system, Segoe UI, Roboto, sans-serif"
    fontSize: "0.8125rem"
    fontWeight: 400
    lineHeight: 1.45
  label:
    fontFamily: "system-ui, -apple-system, Segoe UI, Roboto, sans-serif"
    fontSize: "0.72rem"
    fontWeight: 700
    letterSpacing: "0.06em"
  figure:
    fontFamily: "system-ui, -apple-system, Segoe UI, Roboto, sans-serif"
    fontSize: "1.75rem"
    fontWeight: 700
    lineHeight: 1.15
    letterSpacing: "-0.02em"
    fontFeature: "tnum"
rounded:
  sm: "4px"
  md: "6px"
  lg: "10px"
  pill: "999px"
spacing:
  "1": "4px"
  "2": "8px"
  "3": "12px"
  "4": "16px"
  "5": "20px"
  "6": "28px"
components:
  button-primary:
    backgroundColor: "{colors.harbor-navy}"
    textColor: "{colors.surface}"
    rounded: "{rounded.md}"
    padding: "0 16px"
    height: "36px"
  button-primary-hover:
    backgroundColor: "{colors.harbor-navy-deep}"
  button-secondary:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.md}"
    padding: "0 16px"
    height: "36px"
  button-secondary-hover:
    backgroundColor: "{colors.canvas}"
  button-danger:
    backgroundColor: "{colors.danger-solid}"
    textColor: "{colors.surface}"
    rounded: "{rounded.md}"
    padding: "0 16px"
    height: "36px"
  button-danger-hover:
    backgroundColor: "{colors.danger-solid-deep}"
  button-small:
    rounded: "{rounded.md}"
    padding: "0 12px"
    height: "32px"
  button-disabled:
    backgroundColor: "{colors.rule}"
    textColor: "{colors.slate}"
  button-toggle-pressed:
    backgroundColor: "{colors.info-tint}"
    textColor: "{colors.info-text}"
    rounded: "{rounded.pill}"
  input:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.md}"
    padding: "0 12px"
    height: "36px"
  input-read-only:
    backgroundColor: "{colors.canvas}"
    textColor: "{colors.ink}"
  card:
    backgroundColor: "{colors.surface}"
    rounded: "{rounded.lg}"
    padding: "18px 20px 20px"
  tile:
    backgroundColor: "{colors.surface}"
    rounded: "{rounded.lg}"
    padding: "14px 16px"
  dialog:
    backgroundColor: "{colors.surface}"
    rounded: "{rounded.lg}"
    padding: "20px"
  toast:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.surface}"
    rounded: "{rounded.md}"
    padding: "10px 16px"
  pill-success:
    backgroundColor: "{colors.success-tint}"
    textColor: "{colors.success-text}"
    rounded: "{rounded.pill}"
    padding: "1px 9px"
  pill-warning:
    backgroundColor: "{colors.warning-tint}"
    textColor: "{colors.warning-text}"
    rounded: "{rounded.pill}"
    padding: "1px 9px"
  pill-info:
    backgroundColor: "{colors.info-tint}"
    textColor: "{colors.info-text}"
    rounded: "{rounded.pill}"
    padding: "1px 9px"
  pill-danger:
    backgroundColor: "{colors.danger-tint}"
    textColor: "{colors.danger-text}"
    rounded: "{rounded.pill}"
    padding: "1px 9px"
  pill-neutral:
    backgroundColor: "{colors.neutral-tint}"
    textColor: "{colors.neutral-text}"
    rounded: "{rounded.pill}"
    padding: "1px 9px"
  label-danger:
    backgroundColor: "{colors.danger-tint}"
    textColor: "{colors.danger-text}"
    typography: "{typography.label}"
    rounded: "{rounded.sm}"
    padding: "1px 7px"
---

# Design System: Cite

Version 1.1, 2026-11-25 (D-034, D-035). The frontmatter holds the light values. `design/cite-tokens.css` holds the
light and the dark values and is what each app imports; a test in this repository checks the contrast of both themes.

## Overview

**Creative North Star: "The Calm Control Room"**

Each Cite app is a quiet status room for a small service business. Everything is visible at a glance, and nothing
competes for attention until something needs it. The page is a grey canvas with cards on it; color appears only
where an item needs action, and always next to a word that says why. The feel is quiet and precise: thin borders,
small radii, one soft card shadow, system fonts, and exact figures in tabular numerals.

The reference implementation is the Citebrief morning brief (`templates/brief.css`), approved on 2026-11-25
(D-033). Its shape is the single-page status board: a top bar, a row of summary tiles, then cards in a main column
and a side column. The interactive parts in Components were defined for Citedesk, Citebook, and Citetally and
checked in the Citetally pilot (D-035); the brief page itself has no controls.

**Adopting it.** Copy `design/cite-tokens.css` and this file unchanged, import the CSS file once at the root of the
app, and use only the `--cite-*` names in the app's CSS. Change a value here first, then copy both files again.
**Where an app's own rules require a text, a link, or a flow, the app's rules win over this file;** record the
difference in the app's decision log.

**Key Characteristics:**
- Grey canvas, cards, one soft card shadow.
- Color only for status, always with a word.
- One deep navy main action on each screen.
- System fonts; tabular numerals for every figure and time.
- Light and dark themes from the same tokens.
- Works on a 360 px phone and on paper.

## Colors

A neutral grey base with one deep navy and five status families; every text pair is 4.5:1 or more in both themes.

### Primary
- **Harbor Navy** (`harbor-navy`): the main action button, the brand mark in the top bar, the "current" line of
  tabs and the top bar, and the "info" status. Its deep variant (`harbor-navy-deep`) is the hover state.
- **Link Blue** (`link-blue`): text links and the focus outline. Brighter than the navy, so a link never looks
  like a button.

### Neutral
- **Ink** (`ink`): all body text and headings.
- **Slate** (`slate`): secondary text: captions, column headers, tile labels, help text, footers, disabled text.
- **Surface** (`surface`): cards, tiles, dialogs, the top bar, inputs.
- **Canvas** (`canvas`): the page behind the cards; also read-only inputs.
- **Border** (`border`): the 1px edge of cards and tiles. **Rule** (`rule`): dividers between rows inside a card.
- **Input Border** (`input-border`): the edge of inputs, secondary buttons, and drop zones (3:1 on Surface and on Canvas, WCAG 1.4.11).
- **Neutral** (`neutral-text`, `neutral-tint`): pills and tags for states that need no action ("Waiting",
  "Rejected", "Duplicate").

### Status
- **Danger** (`danger-text`, `danger-tint`, `danger-line`, `danger-solid`, `danger-solid-deep`): safety items,
  failures, destructive actions, and field errors. The solid red is only for the danger button.
- **Success** (`success-text`, `success-tint`): money labels, "Loaded", "confirmed", and the all-clear panel.
- **Info** (`info-text`, `info-tint`): deadline labels, counts that need action, pressed toggle buttons.
- **Warning** (`warning-text`, `warning-tint`, `warning-line`): warning banners, the "Demo data" label, missing
  sources, "worth a look" checks.

### Dark theme
The dark values in `design/cite-tokens.css` apply when the system asks for dark, unless the page root has
`data-theme="light"`; `data-theme="dark"` forces them, so an app with its own theme switch sets that attribute.
Each light color has a dark value with the same role. Citebrief keeps `data-theme="light"`, because the approved
brief and its print copy are light. Primary is also a line color (the current tab, the primary button edge), so it
must reach 3:1 on Surface and on Canvas in both themes.

### Translucency
For a tint over an image or a backdrop, mix a token with transparency
(`color-mix(in srgb, var(--cite-text) 55%, transparent)`); never type a new color. Dialog backdrops use
`--cite-scrim`.

### Named Rules
**The Word-and-Color Rule.** Every status color sits next to a word ("Safety", "Missing", "confirmed"). Color is
never the only signal.

**The Quiet Until Needed Rule.** A tile, row, or card is tinted only when its value needs attention (for example,
the Safety tile when its count is above 0, or a failing check). A screen with nothing to act on is grey and white.

## Typography

**Body Font:** the system UI font (`system-ui`, then Segoe UI, Roboto, sans-serif). No web font is loaded.

**Character:** the platform's own sans: familiar, fast, and legible at small sizes on a phone.

### Hierarchy
- **Headline** (700, 1.75rem, 1.2, -0.02em): one page title, for example "Morning brief". 1.5rem below 30rem.
- **Title** (700, 1rem, 1.3): each card title, section heading, and dialog title.
- **Body** (400, 0.9375rem, 1.55): all text. Lines in cards stay under about 75 characters.
- **Small** (400, 0.8125rem, 1.45): help text, field labels (600 weight), and table notes.
- **Label** (700, 0.72rem, +0.06em, uppercase): tile labels, table column headers, group labels. Never for
  sentences.
- **Figure** (700, 1.75rem, tabular numerals): tile values that are a number or one short word ("Closed").
  A longer value (a date range, a sentence) uses Title size.
- Buttons use 0.875rem, 600 weight.

Each size is a token (`--cite-text-label` to `--cite-text-figure`); apps use the tokens, not typed values.

### Named Rules
**The Tabular Figures Rule.** Every time, amount, count, and ID column uses tabular numerals
(`font-variant-numeric: tabular-nums`), so columns line up.

## Layout

- The page is at most 72rem wide (46rem for a simple list page), with 1.25rem side padding.
- At 60rem and wider, a two-column grid: main column 2fr, side column 1fr, 1rem gap. Below 60rem, one column.
- Summary tiles: 2 columns below 40rem, 4 columns at 40rem and wider.
- Breakpoints for new layouts are 30rem, 40rem, and 60rem. An app may keep breakpoints it already has.
- Spacing steps are 4, 8, 12, 16, 20, and 28px (`--cite-space-1` to `--cite-space-6`). Cards are 16px apart.
  Control heights, card and tile padding, and row padding are tokens too (`--cite-control-height`,
  `--cite-card-padding`, `--cite-tile-padding`, `--cite-row-padding-y`).
- At 360px there is no horizontal page scroll (see Tables for wide tables).
- A fixed bottom action bar leaves the same height of empty space at the end of the page, so it never covers
  content.
- Print: one column, black text on white, no shadows, no colored backgrounds. Each external link (`http`) is
  followed by its address; in-app links (`#/…`) are not.

## Elevation & Depth

The system is flat with two lifts. Cards and tiles sit on the canvas with a 1px border and the card shadow.
Dialogs and toasts, which float over the page, use the overlay shadow. Nothing rises on hover.

### Shadow Vocabulary
- **Card** (`--cite-shadow-card`): cards and tiles only.
- **Overlay** (`--cite-shadow-overlay`): dialogs and toasts only.

### Named Rules
**The Two Shadows Rule.** There are two shadows: card and overlay. Depth comes from the canvas and the card, not
from stacked layers or extra shadows.

## Shapes

Gently rounded and consistent: 4px for small labels and tags, 6px for buttons, inputs, toasts, and panels inside
cards, 10px for cards, tiles, dialogs, and page banners, and fully round for pills, toggle buttons, and status dots.
Borders are 1px; a drop zone uses a 1px dashed border. The brand mark is a 1.4rem navy square with 6px corners.

## Components

### Buttons
Quiet and solid; one main action on each screen.
- **Shape:** 6px corners, `--cite-control-height` (36px), 0 16px padding, 600 weight, 0.875rem. On touch screens,
  keep 44px of tap area by the space around the button.
- **Primary:** Harbor Navy background, white text. Hover: Harbor Navy Deep. One primary button on each screen or
  dialog.
- **Secondary:** Surface background, Ink text, 1px Input Border. Hover: Canvas background.
- **Danger:** Danger Solid background, white text. Hover: Danger Solid Deep. For any action that deletes, cancels,
  or merges records (a merge removes one record), and only with a confirmation step that names the item.
- **Small:** `--cite-control-height-small` (32px), 0 12px padding; for actions inside table rows and check cards.
- **Toggle / filter:** a secondary button with fully round ends and `aria-pressed`. Pressed: Info Tint background,
  Info Text, 1px Harbor Navy border. The word on the button carries the state; the color only repeats it.
- **Focus:** 3px Link Blue outline, 2px offset, on every button.
- **Disabled:** Rule background, Slate text, 1px Rule border, `cursor: not-allowed`; the reason is shown as text
  near the button.
- **Loading:** the button keeps its width, the label changes to the action in progress ("Saving"), and the button
  has `aria-busy="true"` and does not accept a second click.

### Inputs / Fields
- **Style:** Surface background, 1px Input Border, 6px corners, `--cite-control-height`, 0 12px padding, body text.
- **Label:** above the field, Small size, 600 weight, Ink. Help text under the field, Small size, Slate.
- **Focus:** the border changes to Harbor Navy, plus the 3px Link Blue focus outline.
- **Error:** the border is Danger Solid; under the field, a message in Danger Text that names the problem and the
  fix ("Enter a phone number with 10 digits"). The field gets `aria-invalid="true"` and `aria-describedby` to the
  message.
- **Read-only:** Canvas background, Ink text, the normal border; the text stays selectable.
- **Disabled:** Canvas background, Slate text.

### Upload drop zone
A card-sized area with a 1px dashed Input Border, 10px corners, centered Body text, and a secondary button
("Choose files") as the keyboard path. While a file is dragged over it: Info Tint background and a Harbor Navy
border.

### Cards / Containers
- **Corner Style:** 10px.
- **Background:** Surface on the Canvas page.
- **Shadow Strategy:** the Card shadow (Elevation & Depth).
- **Border:** 1px Border.
- **Internal Padding:** `--cite-card-padding` (18px top, 20px sides and bottom; 16px all round below 30rem).
- **Title:** Title type, 12px below it. Rows inside a card are divided by 1px Rule lines; the first row has none.

### Summary tiles
Figures from code. At the top of a board, at most 4 tiles; inside a card, a small group of related figures (for
example "Ready to export"). Label type above, Figure type below (Title size for a long value). A tile is tinted
(Danger Tint with Danger Line, or the Info text color) only under the Quiet Until Needed Rule. A missing source
shows the word "Missing", never 0. Counts that filter a list are toggle buttons, not tiles.

### Pills, tags, and status marks
- **Pill:** fully round, 1px 9px padding, Small size, 600 weight, a tint with its text color: Success (done,
  loaded), Warning (missing, waiting for a person), Info (needs action), Danger (failed), Neutral (no action:
  waiting, rejected, duplicate).
- **Status mark:** a 0.45rem dot in the text color before the word, or an icon from the app's one inline SVG set
  (0.875rem, `currentColor`, `aria-hidden="true"`). Never a mark without a word.
- **Group label / tag:** 4px corners, Label type, the tint and text color of its group (Safety = Danger, Money =
  Success, Deadline = Info; a plain tag is Neutral).

### Lists of items that need attention
A row that needs attention (a failing check, a safety item) gets the tint and line color of its level (Danger or
Warning), a 1px border all round, 6px corners, and its level word ("Must be resolved", "Worth a look"). Rows that
pass stay plain.

### Tables
- Column headers in Label type, Slate, with a 1px Border line under them. Rows have `--cite-row-padding-y` above
  and below, a 1px Rule between rows, and none under the last row. The first column (usually a time) is 600
  weight. Status cells use pills.
- **Narrow screens:** a wide table either scrolls inside its own box, or, below 48rem, shows each row as a small
  card with each value under its column name. Choose one per table; the page itself never scrolls sideways.

### Charts and bar lists
A bar list that compares current values (for example, spend by vendor) is allowed, with the figures as text next
to the bars and a "Show as table" option. No chart of a time series unless the data really is one. A pattern
inside a bar (a stripe made with `repeating-linear-gradient` for a negative value) is a data mark, not a decorative
gradient, and is allowed when a sign or a word also marks the value.

### Navigation
- **Top bar:** Surface, 1px Border under it, the same width as the page. Brand mark and product name on the left;
  plain text links on the right, at most 6. On a phone the links may wrap to a second line. The current page is
  Ink, 600 weight, with a 2px Harbor Navy line under it, and has `aria-current="page"`.
- **Demo notice:** a "Demo data" pill in the top bar, or a full demo sentence in the footer when the app's own
  rules require that sentence. One of the two is always visible.
- **Tabs (only where an app has more than one view):** text links in a row under the page title, with the same
  current-page style as the top bar.

### Dialog
At most 32rem wide (full width minus 16px on a phone), Surface, 10px corners, the Overlay shadow, 20px padding,
over a `--cite-scrim` backdrop. Title type for the heading, Body text, then the actions at the bottom right, the
primary button last. Focus moves into the dialog and stays there; Esc and the cancel button close it. A dialog
only for a choice that needs the user's attention now, never for information.

### Toast
A short confirmation ("Vendor saved"): Ink background, Surface text, 6px corners, the Overlay shadow, 10px 16px
padding, at the bottom center, `role="status"`. It closes after 5 seconds or by its close button. A toast never
carries an error that needs action; errors stay on the page.

### Bottom action bar
For the decisions on one item (for example, approve or reject an invoice): fixed at the bottom of the screen,
Surface background, 1px Border on top, `--cite-space-3` and `--cite-space-5` padding, the actions on the right with
the primary button last.

### Detail panel
For one item opened from a list (an inquiry, a booking, an invoice): a card with a header row (the item title, its
status pill, and its ID in Slate), the item text, then a two-column list of facts (label in Slate, value in Ink).
Actions sit at the bottom of the card or in the bottom action bar, the primary button last on the right. Source
text from a customer is shown as text, never as HTML.

### Banners, empty states, and errors
- **Warning banner:** Warning Tint, 1px Warning Line, 10px corners, Warning Text, at the top of the page content.
- **All-clear panel:** Success Tint, Success Text, 600 weight, 6px corners, for "nothing needs action".
- **Empty state:** inside the card that would hold the items: one plain sentence in Slate that says what is empty
  and, if there is one, one secondary button for the next step.
- **Error state:** a Warning banner that names what failed and what still works; never an empty page.

## Do's and Don'ts

### Do:
- **Do** import `design/cite-tokens.css` and use the `--cite-*` names; never type a hex value in an app's CSS.
- **Do** put a word next to every status color (the Word-and-Color Rule).
- **Do** use one Harbor Navy primary button on each screen.
- **Do** keep a visible 3px focus outline on every link, button, and input.
- **Do** use tabular numerals for times, amounts, counts, and IDs.
- **Do** check every new screen at 360px, in the dark theme, and in print preview.

### Don't:
- **Don't** add a time-series chart without time-series data; a board of current state needs no sparkline.
- **Don't** use a colored side border thicker than 1px on cards, rows, or banners.
- **Don't** add decorative gradients, glass effects, or a third shadow.
- **Don't** use emoji or Unicode symbols as icons; if an app needs icons, use one inline SVG set with one stroke
  weight.
- **Don't** show a count of 0 for a source that is missing; show "Missing".
- **Don't** render model or customer text as HTML.
