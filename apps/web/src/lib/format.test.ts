import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { daysUntil, resetCountdownLabel } from "./format";

const FIXED_NOW = new Date("2026-03-15T12:00:00.000Z");

beforeEach(() => {
  vi.useFakeTimers();
  vi.setSystemTime(FIXED_NOW);
});

afterEach(() => {
  vi.useRealTimers();
});

describe("daysUntil", () => {
  it("rounds up a partial day (23 hours away counts as 1 day, not 0)", () => {
    const target = new Date(FIXED_NOW.getTime() + 23 * 60 * 60 * 1000).toISOString();
    expect(daysUntil(target)).toBe(1);
  });

  it("returns the whole number of days for an exact multi-day gap", () => {
    const target = new Date(FIXED_NOW.getTime() + 5 * 24 * 60 * 60 * 1000).toISOString();
    expect(daysUntil(target)).toBe(5);
  });

  it("clamps a past date to 0 rather than returning a negative number", () => {
    const target = new Date(FIXED_NOW.getTime() - 24 * 60 * 60 * 1000).toISOString();
    expect(daysUntil(target)).toBe(0);
  });

  it("returns 0 for the current instant", () => {
    expect(daysUntil(FIXED_NOW.toISOString())).toBe(0);
  });
});

describe("resetCountdownLabel", () => {
  it("says 'resets today' at 0 days", () => {
    expect(resetCountdownLabel(FIXED_NOW.toISOString())).toBe("resets today");
  });

  it("uses singular 'day' at exactly 1 day", () => {
    const target = new Date(FIXED_NOW.getTime() + 1 * 24 * 60 * 60 * 1000).toISOString();
    expect(resetCountdownLabel(target)).toBe("resets in 1 day");
  });

  it("uses plural 'days' for more than 1 day", () => {
    const target = new Date(FIXED_NOW.getTime() + 16 * 24 * 60 * 60 * 1000).toISOString();
    expect(resetCountdownLabel(target)).toBe("resets in 16 days");
  });
});
