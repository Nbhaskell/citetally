import type { ReactNode } from "react";

import { hrefFor, type Route } from "../lib/router";

export default function Link({
  to,
  children,
  className,
}: {
  to: Route;
  children: ReactNode;
  className?: string;
}) {
  return (
    <a href={hrefFor(to)} className={className}>
      {children}
    </a>
  );
}
