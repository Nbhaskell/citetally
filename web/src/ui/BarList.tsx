import { useId, useState } from "react";

export interface BarRow {
  key: string;
  label: string;
  /** What the bar measures. A negative value (a credit) draws a hatched bar and shows its minus sign. */
  value: number;
  /** The value as words, so no number depends on the bar's length. */
  text: string;
  note?: string;
}

/**
 * A short ranked list of bars, with every value written out and the same rows available as a
 * table. The bar is decoration for the eye; the words and the table are the data.
 */
export default function BarList({
  title,
  rows,
  headers,
  cells,
  empty,
  limit,
}: {
  title: string;
  rows: readonly BarRow[];
  headers: readonly string[];
  cells: (row: BarRow) => string[];
  empty: string;
  /** Show this many first, with a button for the rest. */
  limit?: number;
}) {
  const [asTable, setAsTable] = useState(false);
  const [all, setAll] = useState(false);
  const id = useId();
  const widest = Math.max(1, ...rows.map((row) => Math.abs(row.value)));
  const shown = limit && !all ? rows.slice(0, limit) : rows;

  if (rows.length === 0) {
    return <p className="quiet">{empty}</p>;
  }

  return (
    <div className="bars">
      <div className="bars-tools">
        <button
          type="button"
          className="link-button"
          aria-pressed={asTable}
          aria-controls={id}
          onClick={() => setAsTable((on) => !on)}
        >
          {asTable ? "Show as bars" : "Show as table"}
        </button>
      </div>
      <div id={id}>
        {asTable ? (
          <div className="table-wrap">
            <table className="sample">
              <caption className="sr-only">{title}</caption>
              <thead>
                <tr>
                  {headers.map((header, index) => (
                    <th key={header} scope="col" className={index > 0 ? "num" : undefined}>
                      {header}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {shown.map((row) => (
                  <tr key={row.key}>
                    {cells(row).map((cell, index) => (
                      <td key={index} className={index > 0 ? "num" : undefined}>
                        {cell}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <ul className="bar-rows" aria-label={title}>
            {shown.map((row) => (
              <li key={row.key} title={row.note ? `${row.label}: ${row.text}. ${row.note}` : `${row.label}: ${row.text}`}>
                <span className="bar-label">{row.label}</span>
                <span className="bar-track" aria-hidden="true">
                  <span
                    className={`bar-fill${row.value < 0 ? " bar-negative" : ""}`}
                    style={{ width: `${(Math.abs(row.value) / widest) * 100}%`, minWidth: row.value === 0 ? 0 : undefined }}
                  />
                </span>
                <span className="bar-value">
                  {row.text}
                  {row.note && <span className="quiet"> {row.note}</span>}
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>
      {limit && rows.length > limit && (
        <button type="button" className="link-button" onClick={() => setAll((on) => !on)}>
          {all ? `Show the top ${limit}` : `Show all ${rows.length}`}
        </button>
      )}
    </div>
  );
}
