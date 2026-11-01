import { useMemo, useState } from "react";

import { api, ApiError, type CategoryOut, type VendorOut } from "../api/client";
import { shortDate } from "../lib/time";
import { useApi } from "../lib/useApi";
import Dialog from "../ui/Dialog";
import EmptyState from "../ui/EmptyState";
import Icon from "../ui/Icon";
import Skeleton from "../ui/Skeleton";
import { useToast } from "../ui/Toast";

function describe(error: unknown): string {
  return error instanceof ApiError ? error.message : "Something went wrong. Try again.";
}

function CategorySelect({
  value,
  categories,
  label,
  onChange,
  disabled = false,
}: {
  value: string | null;
  categories: readonly CategoryOut[];
  label: string;
  onChange: (code: string | null) => void;
  disabled?: boolean;
}) {
  return (
    <select
      aria-label={label}
      value={value ?? ""}
      disabled={disabled}
      onChange={(event) => onChange(event.target.value || null)}
    >
      <option value="">None</option>
      {categories
        .filter((c) => c.is_active || c.code === value)
        .map((c) => (
          <option key={c.code} value={c.code}>
            {c.name}
          </option>
        ))}
    </select>
  );
}

function AddVendorDialog({
  categories,
  onDone,
  onCancel,
}: {
  categories: readonly CategoryOut[];
  onDone: (vendor: VendorOut) => void;
  onCancel: () => void;
}) {
  const [name, setName] = useState("");
  const [category, setCategory] = useState<string | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function save() {
    setBusy(true);
    setProblem(null);
    try {
      onDone(await api.createVendor(name.trim(), category));
    } catch (error) {
      setProblem(describe(error));
      setBusy(false);
    }
  }

  return (
    <Dialog title="Add a vendor" onClose={onCancel}>
      <label className="field field-wide">
        <span>Vendor name</span>
        <input type="text" value={name} maxLength={200} onChange={(event) => setName(event.target.value)} />
      </label>
      <label className="field field-wide">
        <span>Default category</span>
        <CategorySelect value={category} categories={categories} label="Default category" onChange={setCategory} />
      </label>
      {problem && (
        <p className="notice notice-block" role="alert">
          <Icon name="alert" /> {problem}
        </p>
      )}
      <div className="dialog-actions">
        <button type="button" className="button" onClick={onCancel}>
          Cancel
        </button>
        <button type="button" className="button button-primary" disabled={busy || name.trim() === ""} onClick={save}>
          Add vendor
        </button>
      </div>
    </Dialog>
  );
}

function AliasDialog({
  vendor,
  onDone,
  onCancel,
}: {
  vendor: VendorOut;
  onDone: (vendor: VendorOut) => void;
  onCancel: () => void;
}) {
  const [alias, setAlias] = useState("");
  const [problem, setProblem] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function save() {
    setBusy(true);
    setProblem(null);
    try {
      onDone(await api.addAlias(vendor.id, alias.trim()));
    } catch (error) {
      setProblem(describe(error));
      setBusy(false);
    }
  }

  return (
    <Dialog title={`Add another name for ${vendor.name}`} onClose={onCancel}>
      <p className="dialog-intro">
        When a document prints this name, it will be matched to {vendor.name} instead of showing up
        as a new vendor.
      </p>
      <label className="field field-wide">
        <span>Name as printed</span>
        <input type="text" value={alias} maxLength={200} onChange={(event) => setAlias(event.target.value)} />
      </label>
      {problem && (
        <p className="notice notice-block" role="alert">
          <Icon name="alert" /> {problem}
        </p>
      )}
      <div className="dialog-actions">
        <button type="button" className="button" onClick={onCancel}>
          Cancel
        </button>
        <button type="button" className="button button-primary" disabled={busy || alias.trim() === ""} onClick={save}>
          Add name
        </button>
      </div>
    </Dialog>
  );
}

function plural(n: number, one: string, many: string): string {
  return `${n} ${n === 1 ? one : many}`;
}

/** The consequence is spelled out before anything happens: merging cannot be taken back here. */
function MergeDialog({
  vendor,
  others,
  onDone,
  onCancel,
}: {
  vendor: VendorOut;
  others: readonly VendorOut[];
  onDone: (into: VendorOut) => void;
  onCancel: () => void;
}) {
  const [targetId, setTargetId] = useState<number | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const target = others.find((v) => v.id === targetId) ?? null;

  async function merge() {
    if (!target) return;
    setBusy(true);
    setProblem(null);
    try {
      onDone(await api.mergeVendor(vendor.id, target.id));
    } catch (error) {
      setProblem(describe(error));
      setBusy(false);
    }
  }

  return (
    <Dialog title={`Merge ${vendor.name} into another vendor`} onClose={onCancel}>
      <label className="field field-wide">
        <span>Merge into</span>
        <select
          value={targetId ?? ""}
          onChange={(event) => setTargetId(event.target.value ? Number(event.target.value) : null)}
        >
          <option value="">Choose a vendor</option>
          {others.map((v) => (
            <option key={v.id} value={v.id}>
              {v.name}
            </option>
          ))}
        </select>
      </label>
      {target && (
        <div className="merge-preview" role="status">
          <p>If you merge:</p>
          <ul>
            <li>
              {plural(vendor.entry_count, "entry", "entries")} will move to {target.name}.
            </li>
            {vendor.waiting_count > 0 && (
              <li>
                {plural(vendor.waiting_count, "entry is", "entries are")} still waiting for review and will be
                checked again.
              </li>
            )}
            <li>
              {vendor.name}
              {vendor.aliases.length > 0 && ` and its ${plural(vendor.aliases.length, "other name", "other names")}`}{" "}
              will become {vendor.aliases.length > 0 ? "names" : "a name"} of {target.name}.
            </li>
            <li>{vendor.name} will be switched off and will no longer appear in the vendor list.</li>
          </ul>
          <p>
            <strong>This cannot be undone from this screen.</strong>
          </p>
        </div>
      )}
      {problem && (
        <p className="notice notice-block" role="alert">
          <Icon name="alert" /> {problem}
        </p>
      )}
      <div className="dialog-actions">
        <button type="button" className="button" onClick={onCancel}>
          Cancel
        </button>
        <button type="button" className="button button-primary" disabled={busy || !target} onClick={merge}>
          {target ? `Merge into ${target.name}` : "Merge"}
        </button>
      </div>
    </Dialog>
  );
}

type Dialogs = { kind: "add" } | { kind: "alias"; vendor: VendorOut } | { kind: "merge"; vendor: VendorOut };

export default function Vendors() {
  const toast = useToast();
  const [text, setText] = useState("");
  const [dialog, setDialog] = useState<Dialogs | null>(null);
  const [saving, setSaving] = useState<number | null>(null);
  const vendors = useApi("vendors", (signal) => api.vendors(signal));
  const categories = useApi("categories", (signal) => api.categories(signal));

  const list = vendors.load.kind === "ready" ? vendors.load.data : null;
  const choices = categories.load.kind === "ready" ? categories.load.data : [];
  const shown = useMemo(() => {
    const needle = text.trim().toLowerCase();
    if (!list) return [];
    if (!needle) return list;
    return list.filter(
      (v) => v.name.toLowerCase().includes(needle) || v.aliases.some((a) => a.toLowerCase().includes(needle)),
    );
  }, [list, text]);

  async function changeCategory(vendor: VendorOut, code: string | null) {
    setSaving(vendor.id);
    try {
      await api.setVendorCategory(vendor.id, code);
      toast.show(
        code
          ? `New documents from ${vendor.name} will start in that category.`
          : `${vendor.name} no longer has a default category.`,
      );
      vendors.reload();
    } catch (error) {
      toast.show(describe(error));
    } finally {
      setSaving(null);
    }
  }

  function finish(message: string) {
    setDialog(null);
    toast.show(message);
    vendors.reload();
  }

  return (
    <>
      <div className="page-head">
        <h1>Vendors</h1>
        <button type="button" className="button button-primary" onClick={() => setDialog({ kind: "add" })}>
          Add a vendor
        </button>
      </div>

      <div className="filters">
        <label className="field">
          <span>Search</span>
          <span className="search">
            <Icon name="search" />
            <input
              type="search"
              value={text}
              placeholder="Name or another name"
              maxLength={100}
              onChange={(event) => setText(event.target.value)}
            />
          </span>
        </label>
      </div>

      {vendors.load.kind === "loading" && <Skeleton rows={5} label="Loading vendors" />}

      {vendors.load.kind === "error" && (
        <EmptyState
          role="alert"
          title="The vendors could not be loaded"
          actions={
            <button type="button" className="button" onClick={vendors.reload}>
              Try again
            </button>
          }
        >
          {vendors.load.error.message}
          {vendors.load.error.requestId ? ` (request ${vendors.load.error.requestId})` : ""}
        </EmptyState>
      )}

      {list && list.length === 0 && (
        <EmptyState
          title="No vendors yet"
          actions={
            <button type="button" className="button button-primary" onClick={() => setDialog({ kind: "add" })}>
              Add a vendor
            </button>
          }
        >
          Vendors are added as you review documents, or you can add one here first.
        </EmptyState>
      )}

      {list && list.length > 0 && shown.length === 0 && (
        <EmptyState
          title="No vendor matches that"
          actions={
            <button type="button" className="button" onClick={() => setText("")}>
              Clear the search
            </button>
          }
        >
          Try part of the name, or another name the vendor prints.
        </EmptyState>
      )}

      {shown.length > 0 && (
        <>
          <p className="sr-only" role="status">
            {plural(shown.length, "vendor", "vendors")} shown
          </p>
          <div className="table-wrap">
            <table className="queue vendors">
              <caption className="sr-only">Vendors</caption>
              <thead>
                <tr>
                  <th scope="col">Vendor</th>
                  <th scope="col">Default category</th>
                  <th scope="col" className="num">
                    Entries
                  </th>
                  <th scope="col">Last invoice</th>
                  <th scope="col">
                    <span className="sr-only">Actions</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {shown.map((vendor) => (
                  <tr key={vendor.id}>
                    <th scope="row" data-label="Vendor" className="cell-vendor">
                      <span className="vendor-name">{vendor.name}</span>
                      {vendor.aliases.length > 0 && (
                        <span className="aliases quiet">Also printed as: {vendor.aliases.join("; ")}</span>
                      )}
                    </th>
                    <td data-label="Default category">
                      <CategorySelect
                        value={vendor.default_category ?? null}
                        categories={choices}
                        label={`Default category for ${vendor.name}`}
                        disabled={saving === vendor.id || categories.load.kind !== "ready"}
                        onChange={(code) => changeCategory(vendor, code)}
                      />
                    </td>
                    <td data-label="Entries" className="num">
                      {vendor.entry_count}
                      {vendor.waiting_count > 0 && (
                        <span className="quiet"> ({vendor.waiting_count} waiting)</span>
                      )}
                    </td>
                    <td data-label="Last invoice">
                      {shortDate(vendor.last_entry_date) || <span className="quiet">–</span>}
                    </td>
                    <td data-label="Actions" className="actions">
                      <button
                        type="button"
                        className="button button-small"
                        onClick={() => setDialog({ kind: "alias", vendor })}
                      >
                        Add another name
                      </button>
                      <button
                        type="button"
                        className="button button-small"
                        disabled={(list?.length ?? 0) < 2}
                        onClick={() => setDialog({ kind: "merge", vendor })}
                      >
                        Merge…
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      {dialog?.kind === "add" && (
        <AddVendorDialog
          categories={choices}
          onCancel={() => setDialog(null)}
          onDone={(vendor) => finish(`${vendor.name} added.`)}
        />
      )}
      {dialog?.kind === "alias" && (
        <AliasDialog
          vendor={dialog.vendor}
          onCancel={() => setDialog(null)}
          onDone={(vendor) => finish(`Documents that print that name will now match ${vendor.name}.`)}
        />
      )}
      {dialog?.kind === "merge" && (
        <MergeDialog
          vendor={dialog.vendor}
          others={(list ?? []).filter((v) => v.id !== dialog.vendor.id)}
          onCancel={() => setDialog(null)}
          onDone={(into) => finish(`Merged into ${into.name}.`)}
        />
      )}
    </>
  );
}
