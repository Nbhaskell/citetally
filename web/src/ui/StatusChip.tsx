import type { DocumentStatus } from "../api/client";
import { STATUS } from "../lib/copy";
import Icon from "./Icon";

/** A status as an icon and a word, never colour alone. */
export default function StatusChip({ status }: { status: DocumentStatus }) {
  const { label, tone, icon } = STATUS[status];
  return (
    <span className={`chip chip-${tone}`} data-status={status}>
      <Icon name={icon} size={14} />
      {label}
    </span>
  );
}
