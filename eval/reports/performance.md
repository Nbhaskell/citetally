# Time per page

Invented documents only. Whole path from upload to the review queue, one document at a time, on one Windows 11 machine with Tesseract and the local `qwen3:8b` model, Python 3.13.15. Made from the saved evaluation runs by `tools/evaluation/performance.py`; no document was processed again.

## development, baseline, 2 passes

| Condition | Documents | Pages | Median s per page | 90th percentile s per page | Slowest document (s) | Median s: read | Median s: model | Failed |
|---|---|---|---|---|---|---|---|---|
| clean pdf | 70 | 70 | 5.3 | 6.3 | 8 | 0.8 | 3.7 | 0 |
| scan light | 72 | 72 | 7.5 | 8.6 | 9 | 2.8 | 3.6 | 0 |
| scan heavy | 70 | 70 | 8.6 | 18.7 | 116 | 3.1 | 4.3 | 4 |
| phone photo | 68 | 68 | 8.0 | 10.2 | 11 | 2.5 | 4.3 | 0 |
| all | 280 | 280 | 7.5 | 10.3 | 116 | 2.6 | 3.8 | 4 |

## held-out, baseline, 1 pass

| Condition | Documents | Pages | Median s per page | 90th percentile s per page | Slowest document (s) | Median s: read | Median s: model | Failed |
|---|---|---|---|---|---|---|---|---|
| clean pdf | 17 | 17 | 5.3 | 6.4 | 7 | 0.8 | 3.5 | 0 |
| scan light | 17 | 17 | 7.5 | 8.4 | 16 | 2.7 | 3.7 | 0 |
| scan heavy | 18 | 18 | 10.5 | 35.9 | 77 | 2.8 | 6.5 | 1 |
| phone photo | 18 | 18 | 7.2 | 8.7 | 11 | 2.6 | 3.6 | 0 |
| all | 70 | 70 | 7.2 | 11.2 | 77 | 2.6 | 3.8 | 1 |

## Reading these

- Every document in the golden set is one page, so seconds per document and per page are the same here. Multi-page documents were not timed.
- In every row the median time in the model is larger than the median time reading.
- The machine was not dedicated to these runs, so read the 90th percentile and the slowest document as typical trouble, not as limits.
- The slowest documents are heavy scans. The failed ones (two scans in both development passes, one in the held-out run) all failed at the model step with "The model's answer could not be used, even after a second try"; the model is asked twice, so these cost about twice a normal answer.
