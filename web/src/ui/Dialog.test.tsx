import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import Dialog from "./Dialog";
import ReasonDialog from "./ReasonDialog";

afterEach(cleanup);

describe("Dialog", () => {
  it("opens as a modal with its title as the name, and closes on Escape and on the backdrop", () => {
    const onClose = vi.fn();
    render(
      <Dialog title="Pick one" onClose={onClose}>
        <button type="button">inside</button>
      </Dialog>,
    );
    const dialog = screen.getByRole("dialog", { name: "Pick one" });
    expect(dialog).toHaveAttribute("open");
    fireEvent(dialog, new Event("cancel", { cancelable: true }));
    expect(onClose).toHaveBeenCalledTimes(1);
    fireEvent.click(dialog); // a click on the backdrop lands on the dialog element itself
    expect(onClose).toHaveBeenCalledTimes(2);
    fireEvent.click(screen.getByText("inside"));
    expect(onClose).toHaveBeenCalledTimes(2);
  });

  it("gives focus back to what opened it", () => {
    function Page() {
      const [open, setOpen] = useState(false);
      return (
        <>
          <button type="button" onClick={() => setOpen(true)}>
            open it
          </button>
          {open && (
            <Dialog title="Hello" onClose={() => setOpen(false)}>
              <button type="button" onClick={() => setOpen(false)}>
                done
              </button>
            </Dialog>
          )}
        </>
      );
    }
    render(<Page />);
    const opener = screen.getByText("open it");
    opener.focus();
    fireEvent.click(opener);
    fireEvent.click(screen.getByText("done"));
    expect(opener).toHaveFocus();
  });

  it("shows text as text", () => {
    render(
      <Dialog title="<b>bold?</b>" onClose={() => undefined}>
        <p>{"<script>x</script>"}</p>
      </Dialog>,
    );
    expect(screen.getByRole("dialog", { name: "<b>bold?</b>" })).toBeInTheDocument();
    expect(document.querySelector("script")).toBeNull();
  });
});

describe("ReasonDialog", () => {
  function setup(props: Partial<Parameters<typeof ReasonDialog>[0]> = {}) {
    const onConfirm = vi.fn();
    const onCancel = vi.fn();
    render(
      <ReasonDialog
        title="Accept this"
        label="Because…"
        minLength={12}
        confirmLabel="Accept"
        onConfirm={onConfirm}
        onCancel={onCancel}
        {...props}
      />,
    );
    return { onConfirm, onCancel };
  }

  it("keeps the button off until the reason is long enough, and says what is needed", () => {
    const { onConfirm } = setup();
    const confirm = screen.getByRole("button", { name: "Accept" });
    expect(confirm).toBeDisabled();
    expect(screen.getByText(/Write at least 12 characters. This will be recorded./)).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Because…"), { target: { value: "too short" } });
    expect(confirm).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Because…"), { target: { value: "  Checked the paper copy.  " } });
    expect(confirm).toBeEnabled();
    expect(screen.getByText("This will be recorded.")).toBeInTheDocument();
    fireEvent.click(confirm);
    expect(onConfirm).toHaveBeenCalledWith("Checked the paper copy.");
  });

  it("does not count spaces as a reason", () => {
    setup();
    fireEvent.change(screen.getByLabelText("Because…"), { target: { value: " ".repeat(30) } });
    expect(screen.getByRole("button", { name: "Accept" })).toBeDisabled();
  });

  it("fills the reason from a quick choice, and Other clears it for typing", () => {
    const { onConfirm } = setup({ quick: ["Not an invoice", "Other"], minLength: 3 });
    fireEvent.click(screen.getByRole("button", { name: "Not an invoice" }));
    expect(screen.getByLabelText("Because…")).toHaveValue("Not an invoice");
    expect(screen.getByRole("button", { name: "Not an invoice" })).toHaveAttribute("aria-pressed", "true");
    fireEvent.click(screen.getByRole("button", { name: "Accept" }));
    expect(onConfirm).toHaveBeenCalledWith("Not an invoice");
    fireEvent.click(screen.getByRole("button", { name: "Other" }));
    expect(screen.getByLabelText("Because…")).toHaveValue("");
  });

  it("cancels without confirming", () => {
    const { onCancel, onConfirm } = setup();
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(onCancel).toHaveBeenCalled();
    expect(onConfirm).not.toHaveBeenCalled();
  });
});
