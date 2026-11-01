// Money arrives as integer minor units and is shown without ever becoming a float:
// the digits are split with BigInt, so $1,240.05 is never 1240.0500000000002.

const SYMBOLS: Record<string, string> = { USD: "$", EUR: "€", GBP: "£", JPY: "¥", CAD: "CA$", AUD: "A$" };
const ZERO_DECIMAL = new Set(["JPY", "KRW", "VND", "CLP", "ISK"]);

const MINUS = "−"; // a real minus sign, which a screen reader says as "minus"

export function decimals(currency: string): number {
  return ZERO_DECIMAL.has(currency) ? 0 : 2;
}

function group(digits: string): string {
  return digits.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
}

export interface MoneyOptions {
  /** A credit note is stored positive and shown negative. */
  credit?: boolean;
  /** Leave the symbol off, for a column whose heading names the currency. */
  bare?: boolean;
}

/** "$1,240.05", "−$45.00", "¥1,500". Null (nothing printed) is an empty string. */
export function formatMinor(
  minor: number | null | undefined,
  currency: string,
  options: MoneyOptions = {},
): string {
  if (minor === null || minor === undefined) return "";
  const places = decimals(currency);
  const negative = (minor < 0) !== Boolean(options.credit) && minor !== 0;
  const absolute = BigInt(Math.abs(minor));
  const scale = 10n ** BigInt(places);
  const whole = group((absolute / scale).toString());
  const fraction = places ? "." + (absolute % scale).toString().padStart(places, "0") : "";
  const symbol = options.bare ? "" : (SYMBOLS[currency] ?? currency + " ");
  return `${negative ? MINUS : ""}${symbol}${whole}${fraction}`;
}

export function symbolFor(currency: string): string {
  return SYMBOLS[currency] ?? currency + " ";
}

export type ParsedAmount = { ok: true; minor: number | null } | { ok: false; why: string };

/**
 * What a person typed in an amount box ("152.00", "$1,240.05", "1240.5") as integer minor units.
 * Empty clears the value. Anything that is not clearly an amount is refused with a reason, so a
 * typo is never saved as a different number.
 */
export function parseMinor(text: string, currency: string): ParsedAmount {
  let t = text.trim().replace(/−/g, "-");
  if (t === "") return { ok: true, minor: null };
  const symbol = SYMBOLS[currency];
  if (symbol && t.startsWith(symbol)) t = t.slice(symbol.length).trim();
  if (t.toUpperCase().startsWith(currency)) t = t.slice(currency.length).trim();
  if (t.startsWith("-")) return { ok: false, why: "An amount cannot be negative here." };
  const places = decimals(currency);
  const pattern = places
    ? /^(\d{1,3}(,\d{3})+|\d+)(\.\d{1,2})?$/
    : /^(\d{1,3}(,\d{3})+|\d+)$/;
  if (!pattern.test(t)) {
    return {
      ok: false,
      why: places ? "Enter an amount like 152.00." : "Enter a whole number like 1500.",
    };
  }
  const [whole, fraction = ""] = t.replace(/,/g, "").split(".");
  const minor = Number(whole) * 10 ** places + Number(fraction.padEnd(places, "0") || "0");
  if (!Number.isSafeInteger(minor) || minor > 10 ** 13) {
    return { ok: false, why: "That amount is too large." };
  }
  return { ok: true, minor };
}

/** Minor units as the plain text of an amount box: "152.00", no symbol, no grouping. */
export function amountInput(minor: number | null | undefined, currency: string): string {
  return minor === null || minor === undefined ? "" : formatMinor(minor, currency, { bare: true }).replace(/,/g, "");
}

/** A stored fraction ("0.0825") as a percentage a person reads ("8.25%"), without floats. */
export function percentText(fraction: string | null | undefined): string {
  if (!fraction || !/^\d+(\.\d+)?$/.test(fraction)) return "";
  const [whole, frac = ""] = fraction.split(".");
  const padded = frac.padEnd(2, "0");
  const shifted = `${whole}${padded.slice(0, 2)}${padded.length > 2 ? "." + padded.slice(2) : ""}`;
  const trimmed = shifted.replace(/^0+(?=\d)/, "").replace(/(\.\d*?)0+$/, "$1").replace(/\.$/, "");
  return `${trimmed}%`;
}

/** A unit price stored as a plain decimal ("4.50"), shown with the currency symbol. */
export function priceText(price: string | null | undefined, currency: string): string {
  return price ? `${symbolFor(currency)}${price}` : "";
}
