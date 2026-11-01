import type { ReactNode } from "react";

import type { Tone } from "../lib/copy";
import Icon from "./Icon";

/** A notice across the page. There is deliberately no close button: hosted mode must stay visible. */
export default function Banner({
  tone = "warn",
  children,
}: {
  tone?: Tone;
  children: ReactNode;
}) {
  return (
    <div className={`banner banner-${tone}`} role="status">
      <Icon name={tone === "block" ? "alert" : "info"} />
      <span>{children}</span>
    </div>
  );
}
