# Demo recording script

A recording of about 60 seconds after editing (57.4 seconds as made). It shows three things: a document that is read and laid out for review, a wrong subtotal from the model that code blocks, and the step where a person approves and makes the CSV file. All steps were run on 2026-11-14 against a new, empty database, the invented documents and the local models (`qwen3:8b` for digital PDFs, `qwen3-vl:8b-instruct` for scans and photos).

Demo data. All vendors, invoices and amounts are invented.

## Before the recording

1. Make the invented documents (about 2.5 minutes), then copy the demo set:

   ```powershell
   .\.venv\Scripts\python.exe -m tools.synthetic.build
   .\.venv\Scripts\python.exe -m tools.synthetic.demo
   ```

2. Start the API on a new, empty database in its own folder, so that the usual database is not changed:

   ```powershell
   $env:CITETALLY_DATA_DIR = "data\demo-recording"
   $env:CITETALLY_DB_PATH = "data\demo-recording\citetally.db"
   .\.venv\Scripts\python.exe -m citetally.db migrate
   .\.venv\Scripts\python.exe -m citetally
   ```

3. In a second terminal, start the web app, then open <http://127.0.0.1:5175>:

   ```powershell
   npm --prefix web run dev
   ```

4. Set the browser window to about 1280 x 800. Hide bookmarks and other tabs.
5. For a second recording, stop the API, delete the folder `data\demo-recording`, and do step 2 again. A file that is already in the list is refused as a duplicate ("Already in the list.").

## Rules for the inputs

- No text is typed in this demo. The inputs are two files, given with the **Choose files** button, and button presses.
- Use these two files only:
  - `data\synthetic\demo\inv-0005.pdf`, a clean invoice as a digital PDF.
  - `data\synthetic\docs\inv-0079.jpg`, a phone photo of an invoice with no planted problem.
- Each document takes 10 to 150 seconds to read. Record everything and cut the waits afterwards. In the recorded run the PDF took 13 seconds and the phone photo took 148 seconds; the model stage of the photo was 141 seconds in the audit records. The same photo took 75 seconds in the practice run. The cause of the difference was not examined.
- The model is local, and a different machine or model version can give a different answer for the phone photo. If the check "Lines don't match the subtotal" does not appear, the model read the subtotal correctly in that run; scene 2 then has nothing to show.

## Scene 1: a document is read (about 15 seconds after cuts)

| Step | Action | What the screen shows |
|---|---|---|
| 1 | On the Inbox, press **Choose files** and give `inv-0005.pdf`. | A row for the file with "Reading the pages…". Cut the wait. |
| 2 | Wait for the status **Needs review**. | The row shows Old Quarry Tool Repair, 14 Jun 2026, $486.49, "1 blocking: New vendor". |
| 3 | Press **Review** in the row. | The page on the left with each found value outlined. On the right, the checks ("New vendor", "13 checks passed") and the details. |
| 4 | Scroll the right side slowly to "Line items" and "Totals as printed". | Three lines, each with the product computed in code ("5 × $72.00 = $360.00"), and "Calculated $480.50" beside the subtotal. |

Caption or narration: "A local model reads the document and copies the printed values. Code finds each value on the page and checks the arithmetic."

## Scene 2: code blocks a wrong model output (about 17 seconds after cuts)

| Step | Action | What the screen shows |
|---|---|---|
| 1 | Go to the Inbox. Press **Choose files** and give `inv-0079.jpg`. | A row for the file. Cut the wait. |
| 2 | Wait for the status **Needs review**. | The row shows "4 blocking, 1 warning". |
| 3 | Press **Review** in the row. | Under "Must be resolved before approving": "Lines don't match the subtotal", "Tax looks off", "Total doesn't add up" and "New vendor". |
| 4 | Stop for three seconds on the first check. | The message quoted below. |
| 5 | Press **Show on page** in the first check. | The box around $117.60 on the page is marked. It is the amount of the second line. The printed subtotal, $142.10, is one row lower. |
| 6 | Move the pointer to **Approve entry**. Do not press it. | The button is disabled. Beside it: "4 checks must be resolved first". |

The message of the first check:

> The lines add up to $142.10. The page says the subtotal is $117.60.

The answer key of the invented document gives a subtotal of $142.10. The model returned $117.60, which is printed on the page as a line amount, so the value was found on the page; the arithmetic checks are what caught it.

Caption or narration: "The model returned a subtotal of $117.60. The page prints $142.10. Code added the lines again and blocked the approval."

## Scene 3: a person approves (about 19 seconds)

| Step | Action | What the screen shows |
|---|---|---|
| 1 | Go to the Inbox. Press **Review** in the row of `inv-0005.pdf`. | One open check: "New vendor". **Approve entry** is disabled. |
| 2 | Press **Pick vendor** in the check. | The dialog "Pick the vendor". |
| 3 | Press **Create vendor “Old Quarry Tool Repair”**. | "Nothing needs attention." and "14 checks passed". **Approve entry** is enabled. |
| 4 | Press **Approve entry**. | A notice that the entry is approved. The next waiting document opens. |
| 5 | Press **Exports** in the top bar. | "Ready to export: 1 approved entry", total $486.49. |
| 6 | Press **Export approved entries**, then **Export 1 entry** in the dialog. | "Your file is ready" with the link "Download citetally_entries_csv_0001.csv" and the line "Import the file into your accounting software yourself." |

Caption or narration: "A person resolves each check and approves. The only output is a CSV file that the person downloads. Nothing is paid, posted or sent."

## Closing frame (6 seconds)

Text on screen: "Sealed test, 300 documents, run once. Header fields exact: 95.3%. Clean documents wrongly blocked: 27.6%, inside the 30% aim. Missed target: a value not located on the page fails 17.2% of clean documents. The aim was 10% for any one check. Demo data: all vendors, invoices and amounts are invented."

The figures are those of `sealed4` in [`eval/reports/eval_sealed4.md`](../eval/reports/eval_sealed4.md).

## How the recording was made and edited

- The scenes were recorded with Playwright (Chromium, 1280 x 800) and cut with ffmpeg. The two scripts, `record_citetally.py` and `edit_citetally.py`, are kept outside this repository.
- Two waits are cut, each to about 1.7 seconds: the read of the PDF in scene 1 (12.6 seconds) and the read of the phone photo in scene 2 (147.6 seconds). Scenes 1 and 2 play at 1.15 times the recorded speed and scene 3 at 1.3 times. Nothing else is changed.
- Three files were made: a video without captions, a video with one caption for each scene in a band below the picture, and an `.srt` caption file.

## Runs

- Recording: one run of the three scenes. All three scenes worked the first time; no scene was recorded again.
- Practice, through the API, before the recording: 14 documents were read (the 12 of the demo set, `inv-0039.pdf` and `inv-0079.jpg`). All 14 reached **Needs review**; none failed.
- `inv-0079.jpg` was read two times (practice and recording). Both times the model returned the same wrong subtotal and the same checks failed. A saved development run gives the same result for this file.

## Inputs that were tried and not used for scene 2

No input failed to be read. These inputs were not used because the model's values were correct, so they do not show a wrong model output. Each result is from the stored checks and the audit records of the practice run.

| File | Result | Reason it was not used |
|---|---|---|
| `inv-0004.jpg` (demo set, phone photo) | `VALUE_IN_DOCUMENT` failed for one line description. | The value equals the answer key. The value was correct but could not be located in the words that the OCR read. |
| `inv-0012.jpg` (demo set, phone photo) | `VALUE_IN_DOCUMENT` failed for the vendor name and one line description. | Both values equal the answer key. The model returned no quantity for the three lines, and no check failed for that. |
| `inv-0002.pdf` (demo set, light scan) | `VALUE_IN_DOCUMENT` failed for the invoice number; `TAX_MATCH` failed. | The invoice number equals the answer key. The tax mismatch is planted in the document, not a model error. |
| `inv-0039.pdf` (development set, heavy scan) | `VALUE_IN_DOCUMENT` failed for several values. | All values equal the answer key in this run. In a saved development run the model misread the total of this file; that did not occur again. |
| `inv-0050.pdf`, `inv-0067.pdf` (demo set, digital PDF) | `LINE_MATH` and `TOTAL_MATCH` failed. | The model copied the values correctly. The errors are planted in the documents. |
