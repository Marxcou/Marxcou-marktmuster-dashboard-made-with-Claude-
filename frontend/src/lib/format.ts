// Alle Zahlen- und Datumsformate zentral: de-DE, Zeitzone Europe/Berlin (Zeitstempel liegen als UTC vor).
const TZ = "Europe/Berlin";

export const formatNumber = (v: number, digits = 2) =>
  new Intl.NumberFormat("de-DE", { minimumFractionDigits: digits, maximumFractionDigits: digits }).format(v);

export const formatPrice = (v: number, currency: string) =>
  new Intl.NumberFormat("de-DE", { style: "currency", currency }).format(v);

export const formatPercent = (fraction: number) =>
  new Intl.NumberFormat("de-DE", { style: "percent", minimumFractionDigits: 2, maximumFractionDigits: 2, signDisplay: "exceptZero" }).format(fraction);

export const formatDateTime = (iso: string) =>
  new Intl.DateTimeFormat("de-DE", { dateStyle: "medium", timeStyle: "medium", timeZone: TZ }).format(new Date(iso));

export const formatDate = (iso: string) =>
  new Intl.DateTimeFormat("de-DE", { dateStyle: "medium", timeZone: TZ }).format(new Date(iso));
