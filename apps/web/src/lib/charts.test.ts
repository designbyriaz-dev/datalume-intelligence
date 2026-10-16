import { describe, expect, it } from "vitest";
import { extractChartData, truncateLabel } from "./charts";

describe("extractChartData", () => {
  it("builds bars from a group_aggregate result", () => {
    const result = {
      group_by: "category",
      value_column: "rent_amount",
      aggregation: "sum",
      groups: [
        { label: "Retail", value: 5000 },
        { label: "Office", value: 3000 },
      ],
    };
    const data = extractChartData("group_aggregate", result);
    expect(data).toEqual({
      caption: "sum by category",
      bars: [
        { label: "Retail", value: 5000 },
        { label: "Office", value: 3000 },
      ],
    });
  });

  it("filters out non-numeric group values rather than crashing", () => {
    const result = {
      group_by: "category",
      aggregation: "sum",
      groups: [
        { label: "Retail", value: 5000 },
        { label: "Unknown", value: null },
      ],
    };
    const data = extractChartData("group_aggregate", result);
    expect(data?.bars).toEqual([{ label: "Retail", value: 5000 }]);
  });

  it("caps group_aggregate bars at 10", () => {
    const result = {
      group_by: "category",
      aggregation: "sum",
      groups: Array.from({ length: 15 }, (_, i) => ({ label: `g${i}`, value: i })),
    };
    const data = extractChartData("group_aggregate", result);
    expect(data?.bars).toHaveLength(10);
  });

  it("builds bars from a frequency_table result", () => {
    const result = {
      column: "status",
      top_values: [
        { value: "Occupied", count: 8, percentage: 80 },
        { value: "Vacant", count: 2, percentage: 20 },
      ],
    };
    const data = extractChartData("frequency_table", result);
    expect(data).toEqual({
      caption: "frequency of status",
      bars: [
        { label: "Occupied", value: 8 },
        { label: "Vacant", value: 2 },
      ],
    });
  });

  it("builds bars from a time_trend result, keeping only the most recent points", () => {
    const result = {
      value_column: "revenue",
      period: "month",
      points: Array.from({ length: 13 }, (_, i) => ({ period: `2026-${String(i + 1).padStart(2, "0")}`, value: i * 100 })),
    };
    const data = extractChartData("time_trend", result);
    expect(data?.bars).toHaveLength(10);
    // points[] is ascending and we keep the tail — so the earliest 3 are dropped.
    expect(data?.bars[0].label).toBe("2026-04");
    expect(data?.bars.at(-1)?.label).toBe("2026-13");
  });

  it("returns null for a shape with no dedicated renderer (e.g. correlation)", () => {
    const result = { column_a: "x", column_b: "y", pearson_r: 0.5, n: 10, scatter_sample: [] };
    expect(extractChartData("correlation", result)).toBeNull();
  });

  it("returns null when result is missing entirely", () => {
    expect(extractChartData("group_aggregate", null)).toBeNull();
    expect(extractChartData("group_aggregate", undefined)).toBeNull();
  });

  it("returns null when the expected array field isn't present", () => {
    expect(extractChartData("group_aggregate", { group_by: "x" })).toBeNull();
  });
});

describe("truncateLabel", () => {
  it("leaves a short label unchanged", () => {
    expect(truncateLabel("Retail", 14)).toBe("Retail");
  });

  it("truncates a long label with an ellipsis, respecting maxLength", () => {
    const result = truncateLabel("A Very Long Category Name", 14);
    expect(result).toBe("A Very Long C…");
    expect(result.length).toBe(14);
  });
});
