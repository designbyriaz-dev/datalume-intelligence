export function daysUntil(isoDate: string): number {
  const diffMs = new Date(isoDate).getTime() - Date.now();
  return Math.max(0, Math.ceil(diffMs / (1000 * 60 * 60 * 24)));
}

export function resetCountdownLabel(resetsAt: string): string {
  const days = daysUntil(resetsAt);
  if (days === 0) return "resets today";
  if (days === 1) return "resets in 1 day";
  return `resets in ${days} days`;
}

const BYTE_UNITS = ["B", "KB", "MB", "GB", "TB"];

export function formatBytes(bytes: number): string {
  if (bytes <= 0) return "0 B";
  const exponent = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), BYTE_UNITS.length - 1);
  const value = bytes / 1024 ** exponent;
  return `${exponent === 0 ? value : value.toFixed(1)} ${BYTE_UNITS[exponent]}`;
}

// Audit log event_type strings are dotted/underscored identifiers
// (e.g. "admin.user_data_accessed", "auth_login_failed") — this turns
// them into plain words for display, left for the caller to capitalize.
export function humanizeEventType(eventType: string): string {
  return eventType.replace(/[._]/g, " ");
}

const MONTH_NAMES = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];

// UsageCounter.period_key is a plain "YYYY-MM" string (app/models/billing.py)
// — parsed with Number(), not `new Date("YYYY-MM")`, since that string is
// parsed as UTC midnight by the Date constructor and can display as the
// previous month in a negative-UTC-offset timezone.
export function formatPeriodKey(periodKey: string): string {
  const [year, month] = periodKey.split("-").map(Number);
  return `${MONTH_NAMES[month - 1]} ${year}`;
}
