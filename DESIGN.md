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
  input-border: "#8a9099"
  harbor-navy: "#173f6b"
  harbor-navy-deep: "#0f2f52"
  link-blue: "#0b4fa3"
  danger-text: "#8a1c1c"
  danger-tint: "#fdeeee"
  danger-line: "#efc4c4"
  danger-solid: "#b42318"
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
  button-disabled:
    backgroundColor: "{colors.rule}"
    textColor: "{colors.slate}"
  input:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.md}"
    padding: "0 12px"
    height: "36px"
  card:
    backgroundColor: "{colors.surface}"
    rounded: "{rounded.lg}"
    padding: "18px 20px 20px"
  tile:
    backgroundColor: "{colors.surface}"
    rounded: "{rounded.lg}"
    padding: "14px 16px"
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
  label-danger:
    backgroundColor: "{colors.danger-tint}"
    textColor: "{colors.danger-text}"
    typography: "{typography.label}"
    rounded: "{rounded.sm}"
    padding: "1px 7px"
---

# Design System: Cite

Version 1.0, 2026-11-25 (D-034). The values in the frontmatter are the same values as in
`design/cite-tokens.css`; that CSS file is what each app imports, and a test in this repository checks its contrast.

## Overview

**Creative North Star: "The Calm Control Room"**

Each Cite app is a quiet status room for a small service business. Everything is visible at a glance, and nothing
competes for attention until something needs it. The page is a light grey canvas with white cards; color appears
only where an item needs action, and always next to a word that says why. The feel is quiet and precise: thin
borders, small radii, one soft shadow, system fonts, and exact figures in tabular numerals.

The reference implementation is the Citebrief morning brief (`templates/brief.css`), approved on 2026-11-25
(D-033). Its shape is the single-page status board: a top bar, a row of summary tiles, then cards in a main column
and a side column. The interactive parts in Components (buttons, inputs, the detail panel, empty and error states)
are defined here for Citedesk, Citebook, and Citetally; the brief page itself has no controls.

To adopt the system in another Cite app, copy `design/cite-tokens.css` and this file unchanged, import the CSS
file once at the root of the app, and map the app's own CSS to the `--cite-*` names. Change a value here first,
then copy both files again.

**Key Characteristics:**
- Light grey canvas, white cards, one soft shadow.
- Color only for status, always with a word.
- One deep navy main action on each screen.
- System fonts; tabular numerals for every figure and time.
- Works on a 360 px phone and on paper.

## Colors

A neutral grey base with one deep navy and four muted status families; every text pair is 4.5:1 or more.

### Primary
- **Harbor Navy** (`harbor-navy`): the main action button, the brand mark in the top bar, and the "info" status.
  Its deep variant (`harbor-navy-deep`) is the hover state.
- **Link Blue** (`link-blue`): text links and the focus outline. Brighter than the navy, so a link never looks
  like a button.

### Neutral
- **Ink** (`ink`): all body text and headings.
- **Slate** (`slate`): secondary text: captions, column headers, tile labels, footers, disabled text.
- **Surface** (`surface`): cards, tiles, the top bar, inputs.
- **Canvas** (`canvas`): the page behind the cards.
- **Border** (`border`): the 1px edge of cards and tiles. **Rule** (`rule`): dividers between rows inside a card.
- **Input Border** (`input-border`): the edge of inputs and secondary buttons (3:1 on white, WCAG 1.4.11).

### Status
- **Danger** (`danger-text`, `danger-tint`, `danger-line`, `danger-solid`): safety items, destructive actions, and
  field errors. The solid red is only for the danger button.
- **Success** (`success-text`, `success-tint`): money labels, "Loaded", "confirmed", and the all-clear panel.
- **Info** (`info-text`, `info-tint`): deadline labels, item counts that need action.
- **Warning** (`warning-text`, `warning-tint`, `warning-line`): warning banners, the "Demo data" label, missing
  sources.

### Named Rules
**The Word-and-Color Rule.** Every status color sits next to a word ("Safety", "Missing", "confirmed"). Color is
never the only signal.

**The Quiet Until Needed Rule.** A tile, row, or card is tinted only when its value needs attention (for example,
the Safety tile when its count is above 0). A screen with nothing to act on is grey and white.

## Typography

**Body Font:** the system UI font (`system-ui`, then Segoe UI, Roboto, sans-serif). No web font is loaded.

**Character:** the platform's own sans: familiar, fast, and legible at small sizes on a phone.

### Hierarchy
- **Headline** (700, 1.75rem, 1.2, -0.02em): one page title, for example "Morning brief". 1.5rem below 30rem.
- **Title** (700, 1rem, 1.3): each card title and section heading.
- **Body** (400, 0.9375rem, 1.55): all text. Lines in cards stay under about 75 characters.
- **Label** (700, 0.72rem, +0.06em, uppercase): tile labels, table column headers, group labels. Never for
  sentences.
- **Figure** (700, 1.75rem, tabular numerals): tile values only.

### Named Rules
**The Tabular Figures Rule.** Every time, amount, count, and ID column uses tabular numerals
(`font-variant-numeric: tabular-nums`), so columns line up.

## Layout

- The page is at most 72rem wide (46rem for a simple list page), with 1.25rem side padding.
- At 60rem and wider, a two-column grid: main column 2fr, side column 1fr, 1rem gap. Below 60rem, one column.
- Summary tiles: 2 columns below 40rem, 4 columns at 40rem and wider; at most 4 tiles.
- Spacing steps are 4, 8, 12, 16, 20, and 28px (`--cite-space-1` to `--cite-space-6`). Cards are 16px apart;
  list rows inside a card have 8px above and below.
- At 360px there is no horizontal page scroll; a wide table scrolls inside its own box.
- Print: one column, black text on white, no shadows, no colored backgrounds, each link followed by its address.

## Elevation & Depth

The system is flat with one lift. Cards and tiles sit on the canvas with a 1px border and one soft ambient shadow;
nothing else has a shadow, and no element rises on hover.

### Shadow Vocabulary
- **Card** (`box-shadow: 0 1px 2px rgba(16, 24, 40, 0.05), 0 2px 6px rgba(16, 24, 40, 0.05)`): cards and tiles
  only.

### Named Rules
**The One Shadow Rule.** There is one shadow in the system. Depth comes from the canvas and the card, not from
stacked layers.

## Shapes

Gently rounded and consistent: 4px for small labels, 6px for buttons, inputs, and banners inside cards, 10px for
cards, tiles, and page banners, and fully round for pills and status dots. Borders are 1px. The brand mark is a
1.4rem navy square with 6px corners.

## Components

### Buttons
Quiet and solid; one main action on each screen.
- **Shape:** 6px corners, 36px high (44px tap target on touch screens by padding around it), 0 16px padding,
  600 weight, 0.875rem.
- **Primary:** Harbor Navy background, white text. Hover: Harbor Navy Deep. One primary button on each screen or
  dialog.
- **Secondary:** white background, ink text, 1px Input Border. Hover: canvas background.
- **Danger:** Danger Solid background, white text. Only for actions that delete or cancel, and only with a
  confirmation step that names the item.
- **Focus:** 3px Link Blue outline, 2px offset, on every button.
- **Disabled:** Rule background, Slate text, no border change, `cursor: not-allowed`; the reason is shown as text
  near the button.
- **Loading:** the button keeps its width, the label changes to the action in progress ("Saving"), and the button
  has `aria-busy="true"` and does not accept a second click.

### Inputs / Fields
- **Style:** white background, 1px Input Border, 6px corners, 36px high, 0 12px padding, body text size.
- **Label:** above the field, 0.8125rem, 600 weight, ink. Help text under the field in Slate.
- **Focus:** the border changes to Harbor Navy, plus the 3px Link Blue focus outline.
- **Error:** the border is Danger Solid; under the field, a message in Danger Text that names the problem and the
  fix ("Enter a phone number with 10 digits"). The field gets `aria-invalid="true"` and `aria-describedby` to the
  message.
- **Disabled:** Canvas background, Slate text.

### Cards / Containers
- **Corner Style:** 10px.
- **Background:** Surface on the Canvas page.
- **Shadow Strategy:** the Card shadow (Elevation & Depth).
- **Border:** 1px Border.
- **Internal Padding:** 18px top, 20px sides and bottom (16px all round below 30rem).
- **Title:** Title type, 12px below it. Rows inside a card are divided by 1px Rule lines; the first row has none.

### Summary tiles
A row of at most 4 figures from code at the top of a board. Label type above, Figure type below. A tile is tinted
(Danger Tint with Danger Line, or the Info text color) only under the Quiet Until Needed Rule. A missing source
shows the word "Missing", never 0.

### Pills and status dots
- **Pill:** fully round, 1px 9px padding, 0.8rem, 600 weight, a tint with its status text color: Success for done
  or loaded, Warning for missing or waiting, Info for "needs action".
- **Status dot:** a 0.45rem dot in the text color before the word, inside the pill. Never a dot without a word.
- **Group label:** 4px corners, Label type, tint and text color of its group (Safety = Danger, Money = Success,
  Deadline = Info).

### Tables
- Column headers in Label type, Slate, with a 1px Border line under them. Rows 10px top and bottom, 1px Rule
  between rows, none under the last row. The first column (usually a time) is 600 weight. Status cells use pills.

### Navigation
- **Top bar:** white, 1px Border under it, the same width as the page. Brand mark and product name on the left;
  the "Demo data" label and plain text links on the right. No more than 4 links; on a phone they stay on one line
  or wrap under the product name.
- **Tabs (only where an app has more than one view):** text links in a row under the page title; the current tab
  is Ink, 600 weight, with a 2px Harbor Navy line under it, and has `aria-current="page"`.

### Detail panel
For one item opened from a list (an inquiry, a booking, an invoice): a card with a header row (the item title, its
status pill, and its ID in Slate), the item text, then a two-column list of facts (label in Slate, value in Ink).
Actions sit at the bottom of the card, the primary button last on the right. Source text from a customer is shown
as text, never as HTML.

### Banners, empty states, and errors
- **Warning banner:** Warning Tint, 1px Warning Line, 10px corners, Warning Text, at the top of the page content.
- **All-clear panel:** Success Tint, Success Text, 600 weight, 8px corners, for "nothing needs action".
- **Empty state:** inside the card that would hold the items: one plain sentence in Slate that says what is empty
  and, if there is one, one secondary button for the next step.
- **Error state:** a Warning banner that names what failed and what still works; never an empty white page.

## Do's and Don'ts

### Do:
- **Do** import `design/cite-tokens.css` and use the `--cite-*` names; never type a hex value in an app's CSS.
- **Do** put a word next to every status color (the Word-and-Color Rule).
- **Do** use one Harbor Navy primary button on each screen.
- **Do** keep a visible 3px focus outline on every link, button, and input.
- **Do** use tabular numerals for times, amounts, counts, and IDs.
- **Do** check every new screen at 360px and in print preview.

### Don't:
- **Don't** add charts unless the data really is a time series; a board of current state needs no sparkline.
- **Don't** use a colored side border thicker than 1px on cards, rows, or banners.
- **Don't** add gradients, glass effects, or a second shadow.
- **Don't** use emoji or Unicode symbols as icons; if an app needs icons, use one inline SVG set with one stroke
  weight.
- **Don't** show a count of 0 for a source that is missing; show "Missing".
- **Don't** render model or customer text as HTML.
