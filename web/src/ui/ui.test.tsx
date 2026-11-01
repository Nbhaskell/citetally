import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { DocumentStatus } from "../api/client";
import { STATUS } from "../lib/copy";
import CheckSummary from "./CheckSummary";
import Money from "./Money";
import StatusChip from "./StatusChip";
import { ToastProvider, useToast } from "./Toast";

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

describe("StatusChip", () => {
  it.each(Object.keys(STATUS) as DocumentStatus[])("%s is a word and an icon, not only a colour", (status) => {
    const { container } = render(<StatusChip status={status} />);
    expect(screen.getByText(STATUS[status].label)).toBeInTheDocument();
    expect(container.querySelector("svg[aria-hidden='true']")).not.toBeNull();
  });
});

describe("Money", () => {
  it("shows an amount with its currency symbol", () => {
    render(<Money minor={124005} currency="USD" />);
    expect(screen.getByText("$1,240.05")).toBeInTheDocument();
  });

  it("marks a credit note with a minus sign and the word Credit", () => {
    render(<Money minor={15200} currency="USD" credit />);
    expect(screen.getByText("−$152.00")).toBeInTheDocument();
    expect(screen.getByText("Credit")).toBeInTheDocument();
  });

  it("says when nothing was read, to a screen reader too", () => {
    render(<Money minor={null} currency="USD" />);
    expect(screen.getByText("Not read from the page")).toBeInTheDocument();
  });

  it("shows zero without a minus or a credit tag", () => {
    render(<Money minor={0} currency="USD" credit />);
    expect(screen.getByText("$0.00")).toBeInTheDocument();
    expect(screen.queryByText("Credit")).toBeNull();
  });
});

describe("CheckSummary", () => {
  const base = { status: "needs_review" as const, unresolved_checks: [], warnings: [] };

  it("says all checks passed", () => {
    render(<CheckSummary row={base} />);
    expect(screen.getByText("All checks passed")).toBeInTheDocument();
  });

  it("counts blocking checks and warnings in words and names them for a screen reader", () => {
    render(
      <CheckSummary
        row={{ ...base, unresolved_checks: ["UNKNOWN_VENDOR", "TOTAL_MATCH"], warnings: ["SUSPICIOUS_TEXT"] }}
      />,
    );
    expect(screen.getByText("2 blocking")).toBeInTheDocument();
    expect(screen.getByText("1 warning")).toBeInTheDocument();
    expect(screen.getByText(/New vendor; Total doesn't add up; The page contains instructions/)).toBeInTheDocument();
  });

  it("has nothing to say before checks have run", () => {
    render(<CheckSummary row={{ ...base, status: "received" }} />);
    expect(screen.getByText("No checks to show")).toBeInTheDocument();
  });
});

function Pusher({ withUndo = false, onUndo = () => undefined }: { withUndo?: boolean; onUndo?: () => void }) {
  const toast = useToast();
  return (
    <button
      type="button"
      onClick={() => toast.show("Saved it.", withUndo ? { label: "Undo", onClick: onUndo } : undefined)}
    >
      push
    </button>
  );
}

describe("Toast", () => {
  it("announces politely, and goes away by itself", () => {
    vi.useFakeTimers();
    render(
      <ToastProvider>
        <Pusher />
      </ToastProvider>,
    );
    fireEvent.click(screen.getByText("push"));
    const region = screen.getByText("Saved it.").closest("[aria-live]");
    expect(region).toHaveAttribute("aria-live", "polite");
    act(() => {
      vi.advanceTimersByTime(8100);
    });
    expect(screen.queryByText("Saved it.")).toBeNull();
  });

  it("offers Undo, runs it once, and closes", () => {
    const undo = vi.fn();
    render(
      <ToastProvider>
        <Pusher withUndo onUndo={undo} />
      </ToastProvider>,
    );
    fireEvent.click(screen.getByText("push"));
    fireEvent.click(screen.getByText("Undo"));
    expect(undo).toHaveBeenCalledTimes(1);
    expect(screen.queryByText("Saved it.")).toBeNull();
  });

  it("can be dismissed, and keeps only the latest few", () => {
    render(
      <ToastProvider>
        <Pusher />
      </ToastProvider>,
    );
    for (let i = 0; i < 5; i += 1) fireEvent.click(screen.getByText("push"));
    expect(screen.getAllByText("Saved it.")).toHaveLength(3);
    fireEvent.click(screen.getAllByText("Dismiss")[0]);
    expect(screen.getAllByText("Saved it.")).toHaveLength(2);
  });

  it("does not run out the clock while the pointer is on it", () => {
    vi.useFakeTimers();
    render(
      <ToastProvider>
        <Pusher />
      </ToastProvider>,
    );
    fireEvent.click(screen.getByText("push"));
    const card = screen.getByText("Saved it.").parentElement as HTMLElement;
    fireEvent.mouseEnter(card);
    act(() => {
      vi.advanceTimersByTime(20_000);
    });
    expect(screen.getByText("Saved it.")).toBeInTheDocument();
    fireEvent.mouseLeave(card);
    act(() => {
      vi.advanceTimersByTime(8100);
    });
    expect(screen.queryByText("Saved it.")).toBeNull();
  });
});
