"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import {
  DndContext,
  KeyboardSensor,
  PointerSensor,
  closestCenter,
  useSensor,
  useSensors,
  type DragEndEvent,
} from "@dnd-kit/core";
import {
  SortableContext,
  arrayMove,
  rectSortingStrategy,
  sortableKeyboardCoordinates,
  useSortable,
} from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { NavBar } from "@/components/NavBar";
import { useAuth } from "@/lib/auth";
import {
  api,
  type Dashboard,
  type DashboardComment,
  type DatasetTable,
  type IndustryPack,
  type ToolSpec,
  ApiError,
} from "@/lib/api";

function WidgetCard({
  widget,
  dragHandleProps,
  onRemove,
  removing,
}: {
  widget: Dashboard["widgets"][number];
  dragHandleProps?: React.HTMLAttributes<HTMLButtonElement>;
  onRemove?: () => void;
  removing?: boolean;
}) {
  const value = widget.value;

  return (
    <div className="rounded-lg border border-slate-200 p-4 dark:border-slate-800">
      <div className="flex items-start justify-between gap-2">
        <div className="text-xs text-slate-500">{widget.title}</div>
        <div className="flex items-center gap-1">
          {dragHandleProps && (
            <button
              type="button"
              {...dragHandleProps}
              aria-label={`Drag to reorder ${widget.title}`}
              title="Drag to reorder"
              className="cursor-grab touch-none rounded px-1 text-slate-300 hover:text-slate-500 active:cursor-grabbing dark:text-slate-600 dark:hover:text-slate-400"
            >
              ⠿
            </button>
          )}
          {onRemove && (
            <button
              type="button"
              onClick={onRemove}
              disabled={removing}
              aria-label={`Remove ${widget.title}`}
              title="Remove widget"
              className="rounded px-1 text-slate-300 hover:text-red-500 disabled:opacity-50 dark:text-slate-600 dark:hover:text-red-400"
            >
              ×
            </button>
          )}
        </div>
      </div>
      {!value ? (
        <div className="mt-1 text-sm text-slate-400">No data</div>
      ) : value.error ? (
        <div className="mt-1 text-sm text-slate-400">Not available: {value.error}</div>
      ) : widget.widget_type === "kpi" ? (
        <div className="mt-1 text-xl font-semibold">{value.formatted}</div>
      ) : (
        <div className="mt-2 overflow-x-auto">
          <pre className="text-xs text-slate-600 dark:text-slate-400">
            {JSON.stringify(value.result, null, 2)}
          </pre>
        </div>
      )}
    </div>
  );
}

function SortableWidgetCard({
  widget,
  onRemove,
  removing,
}: {
  widget: Dashboard["widgets"][number];
  onRemove: () => void;
  removing: boolean;
}) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id: widget.id });

  const style: React.CSSProperties = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1,
  };

  return (
    <div ref={setNodeRef} style={style}>
      <WidgetCard
        widget={widget}
        dragHandleProps={{ ...attributes, ...listeners } as React.HTMLAttributes<HTMLButtonElement>}
        onRemove={onRemove}
        removing={removing}
      />
    </div>
  );
}

function WidgetGrid({
  widgets,
  dashboardId,
  token,
  onReorderError,
  onWidgetRemoved,
}: {
  widgets: Dashboard["widgets"];
  dashboardId: string;
  token: string;
  onReorderError: (message: string) => void;
  onWidgetRemoved: (widgetId: string) => void;
}) {
  // Local copy so a drag can reorder instantly (optimistic) without
  // waiting on the round-trip to persist — reverted on failure.
  const [ordered, setOrdered] = useState(widgets);
  useEffect(() => setOrdered(widgets), [widgets]);
  const [removingId, setRemovingId] = useState<string | null>(null);
  const [removeError, setRemoveError] = useState<string | null>(null);

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 4 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates })
  );

  const onDragEnd = async (event: DragEndEvent) => {
    const { active, over } = event;
    if (!over || active.id === over.id) return;

    const oldIndex = ordered.findIndex((w) => w.id === active.id);
    const newIndex = ordered.findIndex((w) => w.id === over.id);
    if (oldIndex === -1 || newIndex === -1) return;

    const previous = ordered;
    const next = arrayMove(ordered, oldIndex, newIndex);
    setOrdered(next);

    try {
      await api.reorderDashboardWidgets(token, dashboardId, next.map((w) => w.id));
    } catch (err) {
      setOrdered(previous);
      onReorderError(err instanceof ApiError ? err.message : "Could not save the new widget order.");
    }
  };

  const onRemove = async (widgetId: string) => {
    setRemovingId(widgetId);
    setRemoveError(null);
    try {
      await api.removeDashboardWidget(token, dashboardId, widgetId);
      onWidgetRemoved(widgetId);
    } catch (err) {
      setRemoveError(err instanceof ApiError ? err.message : "Could not remove widget.");
    } finally {
      setRemovingId(null);
    }
  };

  return (
    <>
      {removeError && <p className="mt-2 text-xs text-red-600">{removeError}</p>}
      <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={onDragEnd}>
        <SortableContext items={ordered.map((w) => w.id)} strategy={rectSortingStrategy}>
          <div className="mt-6 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {ordered.map((w) => (
              <SortableWidgetCard
                key={w.id}
                widget={w}
                onRemove={() => onRemove(w.id)}
                removing={removingId === w.id}
              />
            ))}
          </div>
        </SortableContext>
      </DndContext>
    </>
  );
}

function AddKpiWidget({
  dashboardId,
  token,
  industryPack,
  onAdded,
}: {
  dashboardId: string;
  token: string;
  industryPack: IndustryPack;
  onAdded: (dashboard: Dashboard) => void;
}) {
  const [kpiId, setKpiId] = useState(industryPack.kpis[0]?.kpi_id ?? "");
  const [adding, setAdding] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (industryPack.kpis.length === 0) return null;

  const onAdd = async () => {
    const kpi = industryPack.kpis.find((k) => k.kpi_id === kpiId);
    if (!kpi) return;
    setAdding(true);
    setError(null);
    try {
      const dashboard = await api.addDashboardWidget(token, dashboardId, {
        widget_type: "kpi",
        title: kpi.name,
        config: { kpi_id: kpi.kpi_id },
      });
      onAdded(dashboard);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not add widget.");
    } finally {
      setAdding(false);
    }
  };

  return (
    <div className="mt-6 flex flex-wrap items-center gap-2 rounded-lg border border-dashed border-slate-300 p-3 dark:border-slate-700">
      <span className="text-sm text-slate-500">Add a KPI widget:</span>
      <select
        value={kpiId}
        onChange={(e) => setKpiId(e.target.value)}
        className="rounded-md border border-slate-300 px-2 py-1 text-sm dark:border-slate-700 dark:bg-slate-900"
      >
        {industryPack.kpis.map((kpi) => (
          <option key={kpi.kpi_id} value={kpi.kpi_id}>
            {kpi.name}
          </option>
        ))}
      </select>
      <button
        type="button"
        onClick={onAdd}
        disabled={adding || !kpiId}
        className="rounded-md bg-brand-500 px-3 py-1 text-sm font-medium text-white hover:bg-brand-600 disabled:opacity-50"
      >
        {adding ? "Adding…" : "Add"}
      </button>
      {error && <p className="w-full text-xs text-red-600">{error}</p>}
    </div>
  );
}

// Every ToolParameter in this registry is one of three shapes: an
// `enum` (a fixed set of choices, e.g. an aggregation function), an
// `"integer"` type (a plain number), or a plain `"string"` with no enum
// — and every one of those plain-string parameters is a column
// reference (column, group_by, value_column, date_column, ...), never
// free text. That's true of all 7 tools in app/services/tools.py today,
// not just the 3 "Generate Dashboard Automatically" happens to use, so
// this form is driven entirely by GET /tools' metadata rather than
// hardcoding a per-operation form — a 8th tool added to that registry
// later needs no frontend change to become addable here.
function ToolParameterField({
  param,
  value,
  onChange,
  columns,
}: {
  param: ToolSpec["parameters"][number];
  value: string;
  onChange: (value: string) => void;
  columns: string[];
}) {
  const label = `${param.name}${param.required ? "" : " (optional)"}`;

  if (param.enum) {
    return (
      <label className="flex flex-col gap-1 text-xs text-slate-500">
        {label}
        <select
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className="rounded-md border border-slate-300 px-2 py-1 text-sm text-slate-900 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
        >
          {param.enum.map((opt) => (
            <option key={opt} value={opt}>
              {opt}
            </option>
          ))}
        </select>
      </label>
    );
  }

  if (param.type === "integer") {
    return (
      <label className="flex flex-col gap-1 text-xs text-slate-500">
        {label}
        <input
          type="number"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className="w-24 rounded-md border border-slate-300 px-2 py-1 text-sm text-slate-900 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
        />
      </label>
    );
  }

  // A plain string parameter — always a column reference in this
  // registry (see the comment above ToolParameterField).
  return (
    <label className="flex flex-col gap-1 text-xs text-slate-500">
      {label}
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="rounded-md border border-slate-300 px-2 py-1 text-sm text-slate-900 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
      >
        {!param.required && <option value="">— none —</option>}
        {columns.map((col) => (
          <option key={col} value={col}>
            {col}
          </option>
        ))}
      </select>
    </label>
  );
}

function defaultParamValues(tool: ToolSpec, columns: string[]): Record<string, string> {
  const values: Record<string, string> = {};
  for (const param of tool.parameters) {
    if (param.default !== null && param.default !== undefined) {
      values[param.name] = String(param.default);
    } else if (param.enum) {
      values[param.name] = param.enum[0] ?? "";
    } else if (param.type !== "integer") {
      values[param.name] = columns[0] ?? "";
    } else {
      values[param.name] = "";
    }
  }
  return values;
}

function AddChartWidget({
  dashboardId,
  token,
  tools,
  table,
  onAdded,
}: {
  dashboardId: string;
  token: string;
  tools: ToolSpec[];
  table: DatasetTable;
  onAdded: (dashboard: Dashboard) => void;
}) {
  const columns = table.profile.columns.map((c) => c.name);
  const [operation, setOperation] = useState(tools[0]?.name ?? "");
  const tool = tools.find((t) => t.name === operation) ?? null;
  const [paramValues, setParamValues] = useState<Record<string, string>>(
    tool ? defaultParamValues(tool, columns) : {}
  );
  const [title, setTitle] = useState("");
  const [adding, setAdding] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (tools.length === 0 || columns.length === 0) return null;

  const onOperationChange = (name: string) => {
    setOperation(name);
    const next = tools.find((t) => t.name === name);
    setParamValues(next ? defaultParamValues(next, columns) : {});
  };

  const onAdd = async () => {
    if (!tool) return;
    setAdding(true);
    setError(null);
    try {
      const parameters: Record<string, unknown> = {};
      for (const param of tool.parameters) {
        const raw = paramValues[param.name];
        if (raw === undefined || raw === "") continue; // omit — required ones get caught server-side
        parameters[param.name] = param.type === "integer" ? Number(raw) : raw;
      }
      const dashboard = await api.addDashboardWidget(token, dashboardId, {
        widget_type: "chart",
        title: title.trim() || tool.name.replace(/_/g, " "),
        config: { operation: tool.name, parameters },
      });
      onAdded(dashboard);
      setTitle("");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not add widget.");
    } finally {
      setAdding(false);
    }
  };

  return (
    <div className="mt-4 flex flex-col gap-2 rounded-lg border border-dashed border-slate-300 p-3 dark:border-slate-700">
      <span className="text-sm text-slate-500">Add a chart widget:</span>
      <div className="flex flex-wrap items-end gap-2">
        <label className="flex flex-col gap-1 text-xs text-slate-500">
          Operation
          <select
            value={operation}
            onChange={(e) => onOperationChange(e.target.value)}
            className="rounded-md border border-slate-300 px-2 py-1 text-sm dark:border-slate-700 dark:bg-slate-900"
          >
            {tools.map((t) => (
              <option key={t.name} value={t.name}>
                {t.name.replace(/_/g, " ")}
              </option>
            ))}
          </select>
        </label>
        {tool?.parameters.map((param) => (
          <ToolParameterField
            key={param.name}
            param={param}
            value={paramValues[param.name] ?? ""}
            onChange={(v) => setParamValues((prev) => ({ ...prev, [param.name]: v }))}
            columns={columns}
          />
        ))}
        <label className="flex flex-col gap-1 text-xs text-slate-500">
          Widget title
          <input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder={tool?.name.replace(/_/g, " ")}
            className="rounded-md border border-slate-300 px-2 py-1 text-sm dark:border-slate-700 dark:bg-slate-900"
          />
        </label>
        <button
          type="button"
          onClick={onAdd}
          disabled={adding || !tool}
          className="rounded-md bg-brand-500 px-3 py-1 text-sm font-medium text-white hover:bg-brand-600 disabled:opacity-50"
        >
          {adding ? "Adding…" : "Add"}
        </button>
      </div>
      {tool && <p className="text-xs text-slate-400">{tool.description}</p>}
      {error && <p className="text-xs text-red-600">{error}</p>}
    </div>
  );
}

function CommentsSection({ dashboardId, token }: { dashboardId: string; token: string }) {
  const [comments, setComments] = useState<DashboardComment[] | null>(null);
  const [text, setText] = useState("");
  const [posting, setPosting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setComments(await api.listComments(token, dashboardId));
    } catch {
      setComments([]);
    }
  }, [token, dashboardId]);

  useEffect(() => {
    load();
  }, [load]);

  const onPost = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!text.trim()) return;
    setPosting(true);
    setError(null);
    try {
      await api.addComment(token, dashboardId, text);
      setText("");
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not post comment.");
    } finally {
      setPosting(false);
    }
  };

  return (
    <div className="mt-8">
      <h2 className="font-medium">Comments</h2>
      {comments === null ? (
        <p className="mt-2 text-sm text-slate-500">Loading…</p>
      ) : comments.length === 0 ? (
        <p className="mt-2 text-sm text-slate-500">No comments yet.</p>
      ) : (
        <ul className="mt-3 space-y-2">
          {comments.map((c) => (
            <li key={c.id} className="rounded-md bg-slate-50 p-3 text-sm dark:bg-slate-900">
              <p>{c.content}</p>
              <p className="mt-1 text-xs text-slate-500">{new Date(c.created_at).toLocaleString()}</p>
            </li>
          ))}
        </ul>
      )}

      <form onSubmit={onPost} className="mt-3 flex gap-2">
        <input
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="Add a comment…"
          className="flex-1 rounded-md border border-slate-300 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-900"
        />
        <button
          type="submit"
          disabled={posting}
          className="rounded-md bg-brand-500 px-4 py-2 text-sm font-medium text-white hover:bg-brand-600 disabled:opacity-50"
        >
          {posting ? "Posting…" : "Post"}
        </button>
      </form>
      {error && <p className="mt-2 text-xs text-red-600">{error}</p>}
    </div>
  );
}

export default function DashboardViewPage() {
  const { token, user, loading } = useAuth();
  const router = useRouter();
  const params = useParams<{ dashboardId: string }>();
  const dashboardId = params.dashboardId;

  const [dashboard, setDashboard] = useState<Dashboard | null>(null);
  const [industryPack, setIndustryPack] = useState<IndustryPack | null>(null);
  const [table, setTable] = useState<DatasetTable | null>(null);
  const [tools, setTools] = useState<ToolSpec[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [reorderError, setReorderError] = useState<string | null>(null);

  useEffect(() => {
    if (!loading && !user) {
      router.push("/login");
    }
  }, [loading, user, router]);

  useEffect(() => {
    if (!token) return;
    api
      .getDashboard(token, dashboardId)
      .then(setDashboard)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Could not load dashboard."));
  }, [token, dashboardId]);

  // The "Add a KPI widget" picker only makes sense for a workspace on
  // one of the four industry packs — a general workspace has no fixed
  // KPI set to pick from (its dashboards stay auto-generate-only, same
  // as before this feature). A pack-less workspace's industry correctly
  // 404s from /industry-packs/{id}, which just means no picker renders.
  useEffect(() => {
    if (!token || !dashboard) return;
    api
      .getWorkspace(token, dashboard.workspace_id)
      .then((workspace) => api.getIndustryPack(token, workspace.industry))
      .then(setIndustryPack)
      .catch(() => setIndustryPack(null));
  }, [token, dashboard?.workspace_id]);

  // The "Add a chart widget" form needs the table's real column names
  // (so parameters are a dropdown, not free text the user has to get
  // exactly right) and the full tool registry (so every operation
  // becomes addable, not just the 3 auto-generate happens to use).
  // Available regardless of industry pack — chart tools work on any
  // table's columns, unlike KPI widgets.
  useEffect(() => {
    if (!token || !dashboard) return;
    api.getDatasetTable(token, dashboard.dataset_table_id).then(setTable).catch(() => setTable(null));
    api.listTools(token).then(setTools).catch(() => setTools([]));
  }, [token, dashboard?.dataset_table_id]);

  const onWidgetRemoved = (widgetId: string) => {
    setDashboard((prev) => (prev ? { ...prev, widgets: prev.widgets.filter((w) => w.id !== widgetId) } : prev));
  };

  if (loading || !user) {
    return (
      <main className="min-h-screen">
        <NavBar />
        <p className="px-6 py-16 text-center text-slate-500">Loading…</p>
      </main>
    );
  }

  return (
    <main className="min-h-screen">
      <NavBar />
      <div className="mx-auto max-w-4xl px-6 py-12">
        <Link href="/dashboard" className="text-sm text-brand-500 hover:underline">
          ← All workspaces
        </Link>

        {error && <p className="mt-4 text-sm text-red-600">{error}</p>}

        {dashboard && (
          <>
            <h1 className="mt-2 text-2xl font-semibold">{dashboard.name}</h1>
            <p className="mt-1 text-sm text-slate-500">
              {dashboard.widgets.length} widget{dashboard.widgets.length === 1 ? "" : "s"} · values computed live
              from the current data · drag ⠿ to reorder, × to remove
            </p>
            {reorderError && <p className="mt-2 text-xs text-red-600">{reorderError}</p>}

            <WidgetGrid
              widgets={dashboard.widgets}
              dashboardId={dashboard.id}
              token={token!}
              onReorderError={setReorderError}
              onWidgetRemoved={onWidgetRemoved}
            />

            {industryPack && (
              <AddKpiWidget
                dashboardId={dashboard.id}
                token={token!}
                industryPack={industryPack}
                onAdded={setDashboard}
              />
            )}

            {table && (
              <AddChartWidget
                dashboardId={dashboard.id}
                token={token!}
                tools={tools}
                table={table}
                onAdded={setDashboard}
              />
            )}

            <CommentsSection dashboardId={dashboard.id} token={token!} />
          </>
        )}
      </div>
    </main>
  );
}
