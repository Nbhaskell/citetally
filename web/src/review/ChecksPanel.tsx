import type { CheckCode, CheckOut, EntryOut, Evidence } from "../api/client";
import { PASSED_TITLE } from "../lib/copy";
import Icon from "../ui/Icon";
import Link from "../ui/Link";
import { explain } from "./explain";
import type { FieldKey } from "./fields";

export type Pending = Partial<Record<CheckCode, string>>;

interface Props {
  checks: readonly CheckOut[];
  entry: EntryOut;
  evidence: readonly Evidence[];
  editable: boolean;
  pending: Pending;
  onShow: (key: FieldKey) => void;
  onShowOnPage: (key: FieldKey) => void;
  onPickVendor: () => void;
  onOverride: (check: CheckOut) => void;
  /** Given when this check can be confirmed against the page picture. */
  canPictureCheck: (check: CheckOut) => boolean;
  onPictureCheck: (check: CheckOut) => void;
  onWithdraw: (code: CheckCode) => void;
}

function CheckItem({
  check,
  entry,
  evidence,
  editable,
  pending,
  onShow,
  onShowOnPage,
  onPickVendor,
  onOverride,
  canPictureCheck,
  onPictureCheck,
  onWithdraw,
}: Props & { check: CheckOut }) {
  const said = explain(check, entry, evidence);
  const reason = pending[check.check_code];
  const onPage = said.target ? evidence.some((e) => e.found && e.x0 !== null && matches(e, said.target!)) : false;
  return (
    <li className={`check check-${check.blocking ? "block" : "warn"}`} id={`check-${check.check_code}`}>
      <div className="check-head">
        <Icon name={check.blocking ? "block" : "alert"} />
        <strong>{said.title}</strong>
        <span className="tag">{check.blocking ? "Must be resolved" : "Worth a look"}</span>
      </div>
      {said.text.map((line) => (
        <p key={line} className="check-text">
          {line}
        </p>
      ))}
      {said.documents.length > 0 && (
        <p className="check-text">
          {said.documents.map((id) => (
            <Link key={id} to={{ name: "review", id }} className="doc-link">
              Open document {id}
            </Link>
          ))}
        </p>
      )}
      {reason ? (
        <p className="check-accepted">
          <Icon name="check" size={14} /> Will be accepted when you approve, because: “{reason}”{" "}
          <button type="button" className="link-button" onClick={() => onWithdraw(check.check_code)}>
            Take back
          </button>
        </p>
      ) : (
        editable && (
          <div className="check-actions">
            {said.target && onPage && (
              <button type="button" className="button button-small" onClick={() => onShowOnPage(said.target!)}>
                Show on page
              </button>
            )}
            {said.target && (
              <button type="button" className="button button-small" onClick={() => onShow(said.target!)}>
                Fix value
              </button>
            )}
            {said.pickVendor && (
              <button type="button" className="button button-small" onClick={onPickVendor}>
                Pick vendor
              </button>
            )}
            {canPictureCheck(check) && (
              <button type="button" className="button button-small" onClick={() => onPictureCheck(check)}>
                Checked against the picture
              </button>
            )}
            {check.blocking && (
              <button type="button" className="button button-small" onClick={() => onOverride(check)}>
                Override with reason
              </button>
            )}
          </div>
        )
      )}
    </li>
  );
}

function matches(e: Evidence, key: FieldKey): boolean {
  const [field, line] = key.split(":");
  return e.field === field && (line === undefined || String(e.line_id) === line);
}

/** What needs doing, in words. Problems that block approval come first; passed checks fold away. */
export default function ChecksPanel(props: Props) {
  const failed = props.checks.filter((c) => !c.passed && !c.overridden);
  const blocking = failed.filter((c) => c.blocking);
  const warnings = failed.filter((c) => !c.blocking);
  const passed = props.checks.filter((c) => c.passed);
  const accepted = props.checks.filter((c) => !c.passed && c.overridden);
  return (
    <section className="checks" aria-labelledby="checks-title">
      <h3 id="checks-title">Checks</h3>
      {blocking.length === 0 && warnings.length === 0 && (
        <p className="checks-clear">
          <Icon name="check" /> Nothing needs attention.
        </p>
      )}
      {blocking.length > 0 && (
        <>
          <h4>Must be resolved before approving</h4>
          <ul className="check-list">
            {blocking.map((c) => (
              <CheckItem key={c.check_code} check={c} {...props} />
            ))}
          </ul>
        </>
      )}
      {warnings.length > 0 && (
        <>
          <h4>Worth a look</h4>
          <ul className="check-list">
            {warnings.map((c) => (
              <CheckItem key={c.check_code} check={c} {...props} />
            ))}
          </ul>
        </>
      )}
      {accepted.length > 0 && (
        <p className="quiet">
          {accepted.length} accepted with a written reason:{" "}
          {accepted.map((c) => `${explain(c, props.entry, props.evidence).title} (“${c.override_reason}”)`).join("; ")}
        </p>
      )}
      <details className="checks-passed">
        <summary>
          {passed.length} {passed.length === 1 ? "check" : "checks"} passed
        </summary>
        <ul>
          {passed.map((c) => (
            <li key={c.check_code}>
              <Icon name="check" size={13} /> {PASSED_TITLE[c.check_code]}
              {c.detail.applicable === false && <span className="quiet"> (nothing to check)</span>}
            </li>
          ))}
        </ul>
      </details>
    </section>
  );
}
