import { useEffect, useState } from "react";

import { fetchStatus, type StatusResponse } from "./api/client";

type State =
  | { kind: "loading" }
  | { kind: "ready"; status: StatusResponse }
  | { kind: "error"; message: string };

function reportedValue(value: boolean | number | string | null | undefined): string {
  return value === null || value === undefined || value === "" ? "not reported yet" : String(value);
}

export default function App() {
  const [state, setState] = useState<State>({ kind: "loading" });

  useEffect(() => {
    const controller = new AbortController();
    fetchStatus(controller.signal).then(
      (status) => setState({ kind: "ready", status }),
      (error: unknown) => {
        if (controller.signal.aborted) return;
        const message =
          error instanceof TypeError
            ? "Cannot reach the API on 127.0.0.1:8200. Start it with: python -m citetally"
            : error instanceof Error
              ? error.message
              : "Something went wrong.";
        setState({ kind: "error", message });
      },
    );
    return () => controller.abort();
  }, []);

  return (
    <>
      {state.kind === "ready" && state.status.hosted_mode && (
        <div className="banner" role="status">
          Hosted model mode: page content is sent to a hosted provider.
        </div>
      )}
      <main>
        <h1>Citetally</h1>
        <p className="tagline">Review desk for invoices and receipts.</p>

        {state.kind === "loading" && <p role="status">Checking the API…</p>}
        {state.kind === "error" && <p role="alert">{state.message}</p>}
        {state.kind === "ready" && (
          <dl className="status">
            <dt>Version</dt>
            <dd>{state.status.version}</dd>
            <dt>Model provider</dt>
            <dd>{state.status.model_provider}</dd>
            <dt>Text model</dt>
            <dd>{state.status.text_model}</dd>
            <dt>Vision model</dt>
            <dd>{state.status.vision_model || "disabled"}</dd>
            <dt>OCR engine</dt>
            <dd>{state.status.ocr_engine}</dd>
            <dt>OCR available</dt>
            <dd>{reportedValue(state.status.ocr_available)}</dd>
            <dt>Database</dt>
            <dd>{reportedValue(state.status.database_ok)}</dd>
            <dt>Queue depth</dt>
            <dd>{reportedValue(state.status.queue_depth)}</dd>
          </dl>
        )}
      </main>
      {state.kind === "ready" && state.status.synthetic_data && (
        <footer>Demo data. All vendors, invoices and amounts are invented.</footer>
      )}
    </>
  );
}
