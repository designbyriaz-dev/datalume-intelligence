export interface ChartBar {
  label: string;
  value: number;
}

export interface ChartData {
  caption: string | null;
  bars: ChartBar[];
}

const MAX_BARS = 10;

// Mirrors app/services/dashboards.py's compute_widget_value: a chart
// widget's raw result shape depends entirely on which of the 7
// app/services/tools.py operations produced it. Only the shapes with an
// obvious single labeled-value series become a bar chart; everything
// else (correlation's scatter_sample, descriptive_stats' flat scalars,
// simple_forecast's two series) falls back to the raw JSON view — a
// deliberately incomplete dispatch rather than a wrong/misleading chart.
export function extractChartData(operation: string | undefined, result: Record<string, unknown> | undefined | null): ChartData | null {
  if (!result) return null;

  if (operation === "group_aggregate" && Array.isArray(result.groups)) {
    const bars = (result.groups as { label: unknown; value: unknown }[])
      .filter((g): g is { label: unknown; value: number } => typeof g.value === "number")
      .slice(0, MAX_BARS)
      .map((g) => ({ label: String(g.label), value: g.value }));
    if (bars.length === 0) return null;
    const groupBy = typeof result.group_by === "string" ? result.group_by : "group";
    const aggregation = typeof result.aggregation === "string" ? result.aggregation : "value";
    return { caption: `${aggregation} by ${groupBy}`, bars };
  }

  if (operation === "frequency_table" && Array.isArray(result.top_values)) {
    const bars = (result.top_values as { value: unknown; count: unknown }[])
      .filter((v): v is { value: unknown; count: number } => typeof v.count === "number")
      .slice(0, MAX_BARS)
      .map((v) => ({ label: String(v.value), value: v.count }));
    if (bars.length === 0) return null;
    const column = typeof result.column === "string" ? result.column : "value";
    return { caption: `frequency of ${column}`, bars };
  }

  if (operation === "time_trend" && Array.isArray(result.points)) {
    const bars = (result.points as { period: unknown; value: unknown }[])
      .filter((p): p is { period: unknown; value: number } => typeof p.value === "number")
      .slice(-MAX_BARS) // most recent periods — points[] is sorted ascending
      .map((p) => ({ label: String(p.period), value: p.value }));
    if (bars.length === 0) return null;
    const valueColumn = typeof result.value_column === "string" ? result.value_column : "value";
    const period = typeof result.period === "string" ? result.period : "period";
    return { caption: `${valueColumn} per ${period}`, bars };
  }

  return null;
}

export function truncateLabel(label: string, maxLength: number): string {
  if (label.length <= maxLength) return label;
  return `${label.slice(0, maxLength - 1)}…`;
}
