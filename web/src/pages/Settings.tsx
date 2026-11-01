import { useState } from "react";

import {
  api,
  ApiError,
  type SelfTestOut,
  type SettingsOut,
  type SettingsUpdate,
} from "../api/client";
import { CHECK_TITLE } from "../lib/copy";
import { useApi } from "../lib/useApi";
import EmptyState from "../ui/EmptyState";
import Icon from "../ui/Icon";
import Skeleton from "../ui/Skeleton";
import { useToast } from "../ui/Toast";

type Values = SettingsOut["values"];

interface Draft {
  default_currency: string;
  locale: string;
  duplicate_date_window_days: string;
  outlier_ratio: string;
  low_confidence: string;
}

function toDraft(values: Values): Draft {
  return {
    default_currency: values.default_currency,
    locale: values.locale,
    duplicate_date_window_days: String(values.duplicate_date_window_days),
    outlier_ratio: values.outlier_ratio,
    low_confidence: String(values.low_confidence),
  };
}

function describe(error: unknown): string {
  return error instanceof ApiError ? error.message : "Something went wrong. Try again.";
}

function yesNo(value: boolean | null | undefined): string {
  return value === null || value === undefined ? "Not known" : value ? "Yes" : "No";
}

/** Only what changed is sent, in the types the API wants. */
function changes(draft: Draft, saved: Values): SettingsUpdate | string {
  const patch: SettingsUpdate = {};
  if (draft.default_currency !== saved.default_currency) patch.default_currency = draft.default_currency.trim();
  if (draft.locale !== saved.locale) patch.locale = draft.locale;
  if (draft.duplicate_date_window_days !== String(saved.duplicate_date_window_days)) {
    const days = Number(draft.duplicate_date_window_days);
    if (!/^\d+$/.test(draft.duplicate_date_window_days.trim()) || days > 60) {
      return "The duplicate window is a whole number of days, from 0 to 60.";
    }
    patch.duplicate_date_window_days = days;
  }
  if (draft.outlier_ratio !== saved.outlier_ratio) patch.outlier_ratio = draft.outlier_ratio.trim();
  if (draft.low_confidence !== String(saved.low_confidence)) {
    const level = Number(draft.low_confidence);
    if (draft.low_confidence.trim() === "" || Number.isNaN(level) || level < 1 || level > 99) {
      return "The read-quality threshold is a number from 1 to 99.";
    }
    patch.low_confidence = level;
  }
  return patch;
}

function Fact({ name, children }: { name: string; children: React.ReactNode }) {
  return (
    <div>
      <dt>{name}</dt>
      <dd>{children}</dd>
    </div>
  );
}

function Setting({
  id,
  label,
  help,
  reset,
  children,
}: {
  id: string;
  label: string;
  help: string;
  reset: React.ReactNode;
  children: (props: { id: string; "aria-describedby": string }) => React.ReactNode;
}) {
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      {children({ id, "aria-describedby": `${id}-help` })}
      <small id={`${id}-help`}>{help}</small>
      {reset}
    </div>
  );
}

function Status({ settings }: { settings: SettingsOut }) {
  const s = settings.status;
  return (
    <section className="insight">
      <h2>How Citetally is set up</h2>
      <p className="quiet">These come from the environment the app was started in. Changing them needs a restart.</p>
      <dl className="facts facts-grid">
        <Fact name="Reading model">
          {s.model_provider === "ollama" ? "On this computer (Ollama)" : "Hosted"}: {s.text_model}
        </Fact>
        <Fact name="Picture model">{s.vision_model ? s.vision_model : "Not used"}</Fact>
        <Fact name="Reading mode">{settings.extract_mode === "text_and_image" ? "Text and page picture" : "Text only"}</Fact>
        <Fact name="Scanning (OCR)">
          {s.ocr_engine === "tesseract" ? "Tesseract" : s.ocr_engine}
          {s.ocr_available === false ? " (not found on this computer)" : ""}
        </Fact>
        <Fact name="Database">{s.database_ok === false ? "Problem: it cannot be opened" : "Working"}</Fact>
        <Fact name="Waiting to be read">{s.queue_depth ?? 0}</Fact>
        <Fact name="Last model use">{s.last_model_call_at ? new Date(s.last_model_call_at).toLocaleString("en-GB") : "None yet"}</Fact>
        <Fact name="Demo data">{yesNo(s.synthetic_data)}</Fact>
        <Fact name="Version">{s.version}</Fact>
      </dl>
      {settings.allow_hosted && (
        <div className={`notice ${s.hosted_mode ? "notice-block" : "notice-warn"}`} role="status">
          <Icon name="alert" />{" "}
          <span>
            <strong>{s.hosted_mode ? "A hosted model is in use." : "Hosted models are allowed here but are not in use."}</strong>{" "}
            A hosted model receives the text of every page it reads, which is sent to a third party. Only use it with
            documents you are allowed to share. It is switched on or off with the environment settings, not here.
          </span>
        </div>
      )}
    </section>
  );
}

function Tuning({ settings, onSaved }: { settings: SettingsOut; onSaved: () => void }) {
  const toast = useToast();
  const [draft, setDraft] = useState<Draft>(() => toDraft(settings.values));
  const [problem, setProblem] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const saved = settings.values;
  const defaults = toDraft(settings.defaults);

  const patch = changes(draft, saved);
  const dirty = typeof patch === "string" || Object.keys(patch).length > 0;
  const set = (name: keyof Draft, value: string) => {
    setDraft((d) => ({ ...d, [name]: value }));
    setProblem(null);
  };

  async function save() {
    if (typeof patch === "string") {
      setProblem(patch);
      return;
    }
    setBusy(true);
    setProblem(null);
    try {
      const next = await api.updateSettings(patch);
      setDraft(toDraft(next.values));
      toast.show("Settings saved. They apply to checks run from now on.");
      onSaved();
    } catch (error) {
      setProblem(describe(error));
    } finally {
      setBusy(false);
    }
  }

  const reset = (name: keyof Draft) =>
    draft[name] !== defaults[name] && (
      <button type="button" className="link-button" onClick={() => set(name, defaults[name])}>
        Back to {defaults[name]}
      </button>
    );

  return (
    <section className="insight">
      <h2>Settings you can change</h2>
      <p className="quiet">
        These tune how the checks behave. They apply to checks run from now on. Documents already checked keep their
        results until they are edited or read again.
      </p>
      <div className="settings-form">
        <Setting
          id="set-currency"
          label="Default currency"
          help="Three letters, such as USD. Used when a document does not name its currency."
          reset={reset("default_currency")}
        >
          {(props) => (
            <input
              {...props}
              type="text"
              value={draft.default_currency}
              maxLength={3}
              onChange={(event) => set("default_currency", event.target.value.toUpperCase())}
            />
          )}
        </Setting>

        <Setting
          id="set-locale"
          label="Date and number order"
          help="Decides how 03/04/2026 is read when it could be March or April."
          reset={reset("locale")}
        >
          {(props) => (
            <select {...props} value={draft.locale} onChange={(event) => set("locale", event.target.value)}>
              {settings.locales.map((code) => (
                <option key={code} value={code}>
                  {code}
                </option>
              ))}
            </select>
          )}
        </Setting>

        <Setting
          id="set-window"
          label="Duplicate window (days)"
          help="Same vendor and total within this many days is flagged as a possible duplicate."
          reset={reset("duplicate_date_window_days")}
        >
          {(props) => (
            <input
              {...props}
              type="text"
              inputMode="numeric"
              value={draft.duplicate_date_window_days}
              onChange={(event) => set("duplicate_date_window_days", event.target.value)}
            />
          )}
        </Setting>

        <Setting
          id="set-ratio"
          label="Unusual amount ratio"
          help="An amount this many times a vendor's usual (or a fraction of it) is flagged. Above 1."
          reset={reset("outlier_ratio")}
        >
          {(props) => (
            <input
              {...props}
              type="text"
              inputMode="decimal"
              value={draft.outlier_ratio}
              onChange={(event) => set("outlier_ratio", event.target.value)}
            />
          )}
        </Setting>

        <Setting
          id="set-read"
          label="Hard-to-read threshold"
          help="Scans read with less confidence than this (out of 100) are flagged as hard to read."
          reset={reset("low_confidence")}
        >
          {(props) => (
            <input
              {...props}
              type="text"
              inputMode="decimal"
              value={draft.low_confidence}
              onChange={(event) => set("low_confidence", event.target.value)}
            />
          )}
        </Setting>
      </div>

      {problem && (
        <p className="notice notice-block" role="alert">
          <Icon name="alert" /> {problem}
        </p>
      )}
      <div className="dialog-actions settings-actions">
        <button type="button" className="button" disabled={!dirty || busy} onClick={() => setDraft(toDraft(saved))}>
          Undo changes
        </button>
        <button type="button" className="button button-primary" disabled={!dirty || busy} onClick={save}>
          Save settings
        </button>
      </div>
    </section>
  );
}

function SelfTest() {
  const [result, setResult] = useState<SelfTestOut | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function run() {
    setBusy(true);
    setProblem(null);
    try {
      setResult(await api.selfTest());
    } catch (error) {
      setResult(null);
      setProblem(describe(error));
    } finally {
      setBusy(false);
    }
  }

  const failed = result?.results.filter((r) => !r.passed).length ?? 0;
  return (
    <section className="insight">
      <h2>Check the checks</h2>
      <p className="quiet">
        Runs the checks on a handful of invented sample documents, each with a known right answer, using the settings
        above. It reads no real documents and changes nothing.
      </p>
      <button type="button" className="button" disabled={busy} onClick={run}>
        Run checks on sample documents
      </button>
      {problem && (
        <p className="notice notice-block" role="alert">
          <Icon name="alert" /> {problem}
        </p>
      )}
      {result && (
        <>
          <p className={`headline ${result.passed ? "" : "headline-bad"}`} role="status">
            {result.passed
              ? `All ${result.results.length} samples came out as expected.`
              : `${failed} of ${result.results.length} samples did not come out as expected.`}
          </p>
          <ul className="selftest" aria-label="Sample results">
            {result.results.map((row) => (
              <li key={row.name} className={row.passed ? "" : "selftest-bad"}>
                <span className="selftest-mark">
                  <Icon name={row.passed ? "check" : "alert"} size={14} />
                  {row.passed ? "As expected" : "Not as expected"}
                </span>
                <span>
                  <strong>{row.name}.</strong> {row.expectation}{" "}
                  <span className="quiet">
                    {row.fired.length === 0
                      ? "No check failed."
                      : `Failed: ${row.fired.map((code) => CHECK_TITLE[code]).join("; ")}.`}
                  </span>
                </span>
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}

export default function Settings() {
  const settings = useApi("settings", (signal) => api.settings(signal));
  const data = settings.load.kind === "ready" ? settings.load.data : null;
  return (
    <>
      <h1>Settings</h1>
      {settings.load.kind === "loading" && <Skeleton rows={5} label="Loading settings" />}
      {settings.load.kind === "error" && (
        <EmptyState
          role="alert"
          title="The settings could not be loaded"
          actions={
            <button type="button" className="button" onClick={settings.reload}>
              Try again
            </button>
          }
        >
          {settings.load.error.message}
          {settings.load.error.requestId ? ` (request ${settings.load.error.requestId})` : ""}
        </EmptyState>
      )}
      {data && (
        <div className="insights-grid">
          <Status settings={data} />
          <Tuning key={JSON.stringify(data.values)} settings={data} onSaved={settings.reload} />
          <SelfTest />
        </div>
      )}
    </>
  );
}
