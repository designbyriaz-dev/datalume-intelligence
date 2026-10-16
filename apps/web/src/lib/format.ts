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
