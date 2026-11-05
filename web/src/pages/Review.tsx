import { useCallback, useMemo, useState } from "react";

import {
  api,
  ApiError,
  type CheckCode,
  type CheckOut,
  type DocumentDetail,
  type EntryLine,
  type EntryPatch,
} from "../api/client";
import { PROCESSING, PROCESSING_STEP, retryStage } from "../lib/copy";
import { navigate } from "../lib/router";
import { useApi } from "../lib/useApi";
import { useShortcuts } from "../lib/useShortcuts";
import ActionBar from "../review/ActionBar";
import ChecksPanel, { type Pending } from "../review/ChecksPanel";
import { ReviewContext, type ReviewApi } from "../review/context";
import DuplicateDialog from "../review/DuplicateDialog";
import EntryForm from "../review/EntryForm";
import { linesWithNoNumbers, linesWithoutQuantity } from "../review/emptyQuantity";
import { evidenceKey, inputId, type FieldKey } from "../review/fields";
import PagePane from "../review/PagePane";
import PictureCheckDialog from "../review/PictureCheckDialog";
import QuantityGateDialog from "../review/QuantityGateDialog";
import { canCheckAgainstPicture, pictureCheckReason, unlocatedValues } from "../review/pictureCheck";
import { explain } from "../review/explain";
import { HistoryDialog, ReprocessDialog, ShortcutHelp } from "../review/SmallDialogs";
import VendorPicker from "../review/VendorPicker";
import EmptyState from "../ui/EmptyState";
import Link from "../ui/Link";
import ReasonDialog from "../ui/ReasonDialog";
import Skeleton from "../ui/Skeleton";
import StatusChip from "../ui/StatusChip";
import { useToast } from "../ui/Toast";

type Dialog =
  | { kind: "vendor" | "reject" | "duplicate" | "reprocess" | "history" | "help" }
  | { kind: "override" | "picture"; check: CheckOut }
  | { kind: "quantity"; lines: EntryLine[]; bare: EntryLine[] }
  | null;

type Saved = { kind: "idle" } | { kind: "saving" } | { kind: "saved"; note: string } | { kind: "error"; message: string };

const REJECT_REASONS = ["Not an invoice", "Unreadable", "Multiple invoices in one file", "Other"];

function describe(error: unknown): string {
  if (error instanceof ApiError) {
    return error.requestId ? `${error.message} (request ${error.requestId})` : error.message;
  }
  return "Something went wrong.";
}

function stampOf(detail: DocumentDetail): string {
  return `${detail.edits.length}:${detail.checks.map((c) => `${c.check_code}${c.passed ? 1 : 0}${c.overridden ? 1 : 0}`).join("")}`;
}

export default function Review({ id }: { id: number }) {
  const toast = useToast();
  const loaded = useApi<DocumentDetail>(`doc:${id}`, (signal) => api.document(id, signal), {
    pollMs: 3000,
    pollWhen: (d) => PROCESSING.includes(d.document.status),
  });
  const categories = useApi("categories", (signal) => api.categories(signal));
  const queue = useApi("queue", (signal) =>
    api.documents({ statuses: ["needs_review"], order: "oldest", limit: 200 }, signal),
  );

  const [local, setLocal] = useState<DocumentDetail | null>(null);
  const [active, setActive] = useState<FieldKey | null>(null);
  const [saved, setSaved] = useState<Saved>({ kind: "idle" });
  const [dialog, setDialog] = useState<Dialog>(null);
  const [pendingState, setPending] = useState<{ stamp: string; map: Pending }>({ stamp: "", map: {} });
  const [openedAt] = useState(() => Date.now());
  const [busy, setBusy] = useState(false);
  const [tab, setTab] = useState<"page" | "details" | "checks">("details");

  const detail: DocumentDetail | null =
    local && local.document.id === id ? local : loaded.load.kind === "ready" ? loaded.load.data : null;
  const entry = detail?.entry ?? null;
  const status = detail?.document.status ?? null;
  const editable = status === "needs_review";

  const pending: Pending = detail && pendingState.stamp === stampOf(detail) ? pendingState.map : {};
  const failedBlocking = useMemo(
    () => (detail?.checks ?? []).filter((c) => c.blocking && !c.passed && !c.overridden),
    [detail],
  );
  const unresolved = failedBlocking.filter((c) => !pending[c.check_code]);

  const evidence = useMemo(
    () => new Map((detail?.evidence ?? []).map((e) => [evidenceKey(e), e] as const)),
    [detail],
  );

  const ids = queue.load.kind === "ready" ? queue.load.data.items.map((r) => r.id) : [];
  const at = ids.indexOf(id);

  const focusKey = useCallback((key: FieldKey) => {
    setActive(key);
    setTab("details");
    window.requestAnimationFrame(() => document.getElementById(inputId(key))?.focus());
  }, []);
  const showKey = useCallback((key: FieldKey) => {
    setActive(key);
    setTab("page");
  }, []);

  const save = useCallback(
    async (patch: EntryPatch): Promise<boolean> => {
      if (!entry) return false;
      setSaved({ kind: "saving" });
      try {
        const next = await api.editEntry(entry.id, patch);
        setLocal(next);
        const open = next.checks.filter((c) => c.blocking && !c.passed && !c.overridden).length;
        setSaved({
          kind: "saved",
          note: open === 0 ? "Saved. Nothing is left to resolve." : `Saved. ${open} ${open === 1 ? "check" : "checks"} must be resolved.`,
        });
        return true;
      } catch (error) {
        setSaved({ kind: "error", message: `Not saved: ${describe(error)}` });
        return false;
      }
    },
    [entry],
  );

  const secondsOpen = () => Math.min(86_400, Math.round((Date.now() - openedAt) / 1000));

  function leave(afterId: number, message: string, undo?: () => Promise<void>) {
    const others = ids.filter((x) => x !== afterId);
    const index = ids.indexOf(afterId);
    const next = others[index] ?? others[others.length - 1] ?? null; // the one after, else the one before
    toast.show(message, undo ? { label: "Undo", onClick: () => void undo() } : undefined);
    if (next !== null) navigate({ name: "review", id: next });
    else {
      toast.show("That was the last one waiting.");
      navigate({ name: "inbox" });
    }
  }

  async function run(action: () => Promise<void>) {
    setBusy(true);
    try {
      await action();
    } catch (error) {
      toast.show(describe(error));
      setLocal(null);
      loaded.reload();
    } finally {
      setBusy(false);
    }
  }

  const undoTo = (reopenId: number) => async () => {
    try {
      await api.reopen(reopenId);
      navigate({ name: "review", id: reopenId });
      queue.reload();
      toast.show("Reopened.");
    } catch (error) {
      toast.show(describe(error));
    }
  };

  const approve = () =>
    run(async () => {
      if (!entry) return;
      const overrides = failedBlocking.map((c) => ({
        check_code: c.check_code,
        reason: pending[c.check_code] ?? "",
      }));
      await api.approve(id, overrides, secondsOpen());
      leave(id, `Approved ${entry.invoice_number ?? "the entry"}.`, undoTo(id));
    });

  /** Approve, but first ask about lines with no quantity: nothing else flags them. */
  const requestApprove = () => {
    const empty = entry ? linesWithoutQuantity(entry.lines) : [];
    const bare = entry ? linesWithNoNumbers(entry.lines) : [];
    if (empty.length > 0 || bare.length > 0) setDialog({ kind: "quantity", lines: empty, bare });
    else void approve();
  };

  const reject = (reason: string) =>
    run(async () => {
      setDialog(null);
      await api.reject(id, reason, secondsOpen());
      leave(id, "Rejected.", undoTo(id));
    });

  const markDuplicate = (originalId: number) =>
    run(async () => {
      setDialog(null);
      await api.markDuplicate(id, originalId, secondsOpen());
      leave(id, `Set aside as a duplicate of document ${originalId}.`);
    });

  const reopen = () =>
    run(async () => {
      await api.reopen(id);
      setLocal(null);
      loaded.reload();
      queue.reload();
      toast.show("Reopened. You can edit it again.");
    });

  const reprocess = (from: "read" | "extract") =>
    run(async () => {
      setDialog(null);
      await api.reprocess(id, from);
      setLocal(null);
      loaded.reload();
      toast.show("Started again. This page updates by itself.");
    });

  const canApprove = editable && unresolved.length === 0;
  useShortcuts(
    {
      j: () => ids[at + 1] !== undefined && navigate({ name: "review", id: ids[at + 1] }),
      k: () => at > 0 && navigate({ name: "review", id: ids[at - 1] }),
      a: () => canApprove && !busy && requestApprove(),
      r: () => editable && setDialog({ kind: "reject" }),
      e: () => editable && document.getElementById(inputId("invoice_number"))?.focus(),
      "g p": () => document.querySelector<HTMLElement>(".page-scroll")?.focus(),
      "?": () => setDialog({ kind: "help" }),
    },
    detail !== null,
  );

  // ---- states before there is anything to review ------------------------------------------

  if (loaded.load.kind === "loading" && !detail) return <Skeleton rows={6} label="Loading the document" />;
  if (loaded.load.kind === "error" && !detail) {
    const notFound = loaded.load.error.code === "not_found";
    return (
      <EmptyState
        role="alert"
        title={notFound ? "That document does not exist" : "The document could not be loaded"}
        actions={
          notFound ? (
            <Link to={{ name: "inbox" }} className="button">
              Back to the Inbox
            </Link>
          ) : (
            <button type="button" className="button" onClick={loaded.reload}>
              Try again
            </button>
          )
        }
      >
        {loaded.load.error.message}
        {loaded.load.error.requestId ? ` (request ${loaded.load.error.requestId})` : ""}
      </EmptyState>
    );
  }
  if (!detail || !status) return null;

  const doc = detail.document;
  const processing = PROCESSING.includes(status);

  const api2: ReviewApi | null = entry
    ? {
        entry,
        currency: entry.currency ?? "USD",
        editable,
        evidence,
        categories: categories.load.kind === "ready" ? categories.load.data : [],
        activeKey: active,
        setActive,
        focusKey,
        showKey,
        save,
        openVendorPicker: () => setDialog({ kind: "vendor" }),
      }
    : null;

  return (
    <div className="review" data-tab={tab}>
      <header className="review-head">
        <p className="crumbs">
          <Link to={{ name: "inbox" }}>Inbox</Link>
          {at >= 0 && (
            <span className="quiet">
              {" "}
              · {at + 1} of {ids.length} waiting
            </span>
          )}
        </p>
        <h1 className="review-title">
          <span className="clip-wrap">{doc.original_filename}</span> <StatusChip status={status} />
        </h1>
        <p className="save-state" role="status" aria-live="polite">
          {saved.kind === "saving" && "Saving…"}
          {saved.kind === "saved" && saved.note}
          {saved.kind === "error" && <span className="save-error">{saved.message}</span>}
        </p>
      </header>

      {processing && (
        <EmptyState role="status" title={`${PROCESSING_STEP[status]}…`}>
          This document is still being read. This page updates by itself.
        </EmptyState>
      )}

      {status === "failed" && (
        <EmptyState
          role="alert"
          title="This document could not be read"
          actions={
            retryStage(doc.failure_stage) ? (
              <button type="button" className="button button-primary" onClick={() => setDialog({ kind: "reprocess" })}>
                Reprocess…
              </button>
            ) : undefined
          }
        >
          {doc.failure_message ?? "Something went wrong."}
        </EmptyState>
      )}

      {status === "duplicate" && doc.duplicate_of !== null && (
        <EmptyState title="Set aside as a duplicate">
          This is the same as <Link to={{ name: "review", id: doc.duplicate_of }}>document {doc.duplicate_of}</Link>. It will not be
          exported.
        </EmptyState>
      )}

      {entry && api2 && (
        <ReviewContext.Provider value={api2}>
          <div className="review-tabs" role="group" aria-label="Show">
            {(["page", "details", "checks"] as const).map((name) => (
              <button
                key={name}
                type="button"
                className="button"
                aria-pressed={tab === name}
                onClick={() => setTab(name)}
              >
                {name === "page" ? "Page" : name === "details" ? "Details" : `Checks${unresolved.length ? ` (${unresolved.length})` : ""}`}
              </button>
            ))}
          </div>
          <div className="review-grid">
            <PagePane pages={detail.pages} evidence={detail.evidence} entry={entry} activeKey={active} onPick={focusKey} />
            <div className="review-side">
              {!editable && (
                <p className="notice notice-info">
                  {status === "exported"
                    ? "This entry was exported, so it can no longer be changed."
                    : status === "approved"
                      ? "Approved. Reopen it to make changes."
                      : status === "rejected"
                        ? "Rejected. Reopen it to review it again."
                        : "Read only."}
                </p>
              )}
              <ChecksPanel
                checks={detail.checks}
                entry={entry}
                evidence={detail.evidence}
                editable={editable}
                pending={pending}
                onShow={focusKey}
                onShowOnPage={showKey}
                onPickVendor={() => setDialog({ kind: "vendor" })}
                onOverride={(check) => setDialog({ kind: "override", check })}
                canPictureCheck={(check) => canCheckAgainstPicture(check, detail)}
                onPictureCheck={(check) => setDialog({ kind: "picture", check })}
                onWithdraw={(code: CheckCode) => setPending({ stamp: stampOf(detail), map: { ...pending, [code]: undefined } })}
              />
              <EntryForm lines={entry.lines} checks={detail.checks} />
            </div>
          </div>
        </ReviewContext.Provider>
      )}

      <ActionBar
        status={status}
        unresolved={unresolved.length}
        busy={busy || processing}
        onApprove={requestApprove}
        onReject={() => setDialog({ kind: "reject" })}
        onDuplicate={() => setDialog({ kind: "duplicate" })}
        onReprocess={() => setDialog({ kind: "reprocess" })}
        onReopen={() => void reopen()}
        onHistory={() => setDialog({ kind: "history" })}
      />

      {dialog?.kind === "reject" && (
        <ReasonDialog
          title="Reject this document"
          label="Why is it being rejected?"
          quick={REJECT_REASONS}
          minLength={3}
          confirmLabel="Reject document"
          onConfirm={(reason) => void reject(reason)}
          onCancel={() => setDialog(null)}
        />
      )}
      {dialog?.kind === "override" && entry && (
        <ReasonDialog
          title={explain(dialog.check, entry, detail.evidence).title}
          intro={explain(dialog.check, entry, detail.evidence).text.map((line) => (
            <p key={line}>{line}</p>
          ))}
          label="I've checked this and it's correct because…"
          minLength={12}
          confirmLabel="Accept this check"
          note="This will be recorded."
          onConfirm={(reason) => {
            const code = dialog.check.check_code;
            setPending({ stamp: stampOf(detail), map: { ...pending, [code]: reason } });
            setDialog(null);
          }}
          onCancel={() => setDialog(null)}
        />
      )}
      {dialog?.kind === "picture" && (
        <PictureCheckDialog
          values={unlocatedValues(dialog.check)}
          onConfirm={() => {
            const code = dialog.check.check_code;
            const reason = pictureCheckReason(unlocatedValues(dialog.check).length);
            setPending({ stamp: stampOf(detail), map: { ...pending, [code]: reason } });
            setDialog(null);
          }}
          onCancel={() => setDialog(null)}
        />
      )}
      {dialog?.kind === "quantity" && (
        <QuantityGateDialog
          lines={dialog.lines}
          bare={dialog.bare}
          onBack={() => setDialog(null)}
          onApprove={() => {
            setDialog(null);
            void approve();
          }}
        />
      )}
      {dialog?.kind === "vendor" && entry && (
        <VendorPicker
          entry={entry}
          onClose={() => setDialog(null)}
          onChoose={async (choice) => {
            const next = await api.chooseVendor(entry.id, choice);
            setLocal(next);
            setDialog(null);
            toast.show(`Vendor set to ${next.entry?.vendor_name ?? "the chosen vendor"}.`);
          }}
        />
      )}
      {dialog?.kind === "duplicate" && (
        <DuplicateDialog
          current={{
            ...doc,
            entry_id: entry?.id ?? null,
            entry_type: entry?.entry_type ?? null,
            vendor_name: entry?.vendor_name ?? entry?.vendor_name_raw ?? null,
            invoice_number: entry?.invoice_number ?? null,
            entry_date: entry?.entry_date ?? null,
            currency: entry?.currency ?? null,
            total_minor: entry?.total_minor ?? null,
            unresolved_checks: [],
            warnings: [],
          }}
          onConfirm={(original) => void markDuplicate(original)}
          onClose={() => setDialog(null)}
        />
      )}
      {dialog?.kind === "reprocess" && <ReprocessDialog onConfirm={(from) => void reprocess(from)} onClose={() => setDialog(null)} />}
      {dialog?.kind === "history" && <HistoryDialog detail={detail} onClose={() => setDialog(null)} />}
      {dialog?.kind === "help" && <ShortcutHelp onClose={() => setDialog(null)} />}
    </div>
  );
}
