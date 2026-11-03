# Security

Citetally is a single-user tool that runs on one person's own machine. All data in this repository is invented.

## What it is and is not

- **It binds to `127.0.0.1` only and has no login.** Do not put it on a network, a shared server or the internet as it stands. Anyone who can reach the port can read and change everything in it.
- **Nothing is paid, posted or sent.** The only output is a CSV file the person downloads.
- **Hosted models are off by default** (`CITETALLY_ALLOW_HOSTED=false`). With the defaults, documents are read by local programs (Tesseract and Ollama) and nothing leaves the machine.
- **Uploaded files and the text in them are treated as untrusted.** Type is checked by content, size, page and pixel limits are enforced, parsing runs in a separate process with timeouts, and nothing embedded is executed. Model output and document text are shown as text, never as HTML. Instruction-like text in a document is flagged and ignored. The rules and how they are tested are in [`docs/HARDENING.md`](docs/HARDENING.md).
- **It has not been run on real business documents.** The evaluation used invented ones; see the README for what that does and does not show.

## Reporting a problem

Please report a security problem privately, with GitHub's "Report a vulnerability" button on this repository's Security tab, and not in a public issue. Include what you did, what you expected and what happened. Do not attach real documents or real personal data.

This is a personal project, so there is no guaranteed response time and no supported versions other than the latest commit on `main`.
