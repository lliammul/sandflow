"use client";

import clsx from "clsx";
import { useEffect, useState, useTransition } from "react";

import { sidecar } from "../lib/sidecar";
import type {
  ArtifactOutputDefinition,
  InputFieldDefinition,
  OutputFieldDefinition,
  WorkflowDefinition,
  WorkflowRegistryEntry,
} from "../lib/types";
import { AppShell, Banner } from "./app-shell";
import {
  Badge,
  Field,
  IconChevronDown,
  IconChevronUp,
  IconCopy,
  IconPlus,
  IconSave,
  IconTrash,
  Panel,
  PanelHeader,
} from "./shared";

type SchemaRow = InputFieldDefinition | OutputFieldDefinition | ArtifactOutputDefinition;

function createDraft(): WorkflowDefinition {
  const now = new Date().toISOString();
  return {
    schema_version: 1,
    id: "workflow",
    name: "New Workflow",
    description: "",
    is_active: true,
    prompt: "Describe what this workflow should do.",
    input_fields: [{ id: "input_1", label: "Input", type: "short_text", required: true, help_text: "" }],
    output_fields: [{ id: "output_1", label: "Result", type: "text", required: true, help_text: "" }],
    artifact_outputs: [],
    created_at: now,
    updated_at: now,
  };
}

export function BuilderConsole() {
  const [entries, setEntries] = useState<WorkflowRegistryEntry[]>([]);
  const [workflowMap, setWorkflowMap] = useState<Record<string, WorkflowDefinition>>({});
  const [draft, setDraft] = useState<WorkflowDefinition>(createDraft);
  const [selectedId, setSelectedId] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [isPending, startTransition] = useTransition();
  const [promptCollapsed, setPromptCollapsed] = useState(false);

  useEffect(() => {
    let active = true;
    const load = async () => {
      try {
        const [items, workflows] = await Promise.all([
          sidecar.getWorkflowEntries(true),
          sidecar.getWorkflows(true),
        ]);
        if (!active) {
          return;
        }
        const nextWorkflowMap = Object.fromEntries(workflows.map((workflow) => [workflow.id, workflow]));
        setEntries(items);
        setWorkflowMap(nextWorkflowMap);
        if (items[0] && !items[0].has_error && nextWorkflowMap[items[0].id]) {
          setSelectedId(items[0].id);
          setDraft(nextWorkflowMap[items[0].id]);
        }
      } catch (event) {
        if (!active) {
          return;
        }
        setError(extractMessage(event, "Failed to load workflow entries."));
      }
    };
    void load();
    const onReady = () => {
      void load();
    };
    window.addEventListener("sandflow:runtime-ready", onReady);
    return () => {
      active = false;
      window.removeEventListener("sandflow:runtime-ready", onReady);
    };
  }, []);

  const reloadEntries = async () => {
    const [items, workflows] = await Promise.all([
      sidecar.getWorkflowEntries(true),
      sidecar.getWorkflows(true),
    ]);
    setEntries(items);
    setWorkflowMap(Object.fromEntries(workflows.map((workflow) => [workflow.id, workflow])));
    return { items, workflows };
  };

  const sidebar = (
    <div className="panel">
      <div className="flex items-center justify-between border-b border-[color:var(--line)] px-4 py-3">
        <div className="monoline">Workflows</div>
        <button
          type="button"
          className="btn btn-ghost px-2 py-1 text-xs"
          onClick={() => {
            setSelectedId("");
            setDraft(createDraft());
            setNotice("New workflow draft ready.");
          }}
          aria-label="New workflow"
        >
          <IconPlus size={12} />
          New
        </button>
      </div>
      <div className="divide-y divide-[color:var(--line-soft)]">
        {entries.length ? (
          entries.map((entry) => (
            <button
              key={entry.id}
              onClick={async () => {
                setSelectedId(entry.id);
                setNotice("");
                setError("");
                if (entry.has_error) {
                  return;
                }
                const workflow = workflowMap[entry.id] ?? (await sidecar.getWorkflow(entry.id));
                setWorkflowMap((current) => ({ ...current, [entry.id]: workflow }));
                setDraft(workflow);
              }}
              className={clsx(
                "block w-full px-4 py-3 text-left transition",
                entry.id === selectedId ? "bg-[color:var(--accent-soft)]" : "hover:bg-[color:var(--surface-muted)]",
              )}
            >
              <div className="flex items-center justify-between gap-2">
                <div className="flex min-w-0 items-center gap-2">
                  <span
                    aria-hidden
                    className={clsx(
                      "inline-block h-2 w-2 flex-none rounded-full",
                      entry.has_error
                        ? "bg-[color:var(--danger)]"
                        : entry.is_active
                          ? "bg-[color:var(--accent)]"
                          : "bg-[color:var(--line-soft)]",
                    )}
                  />
                  <div className="truncate text-sm font-semibold">{entry.name}</div>
                </div>
                <span className="mono truncate text-[10px] text-[color:var(--subtle)]">{entry.id}</span>
              </div>
              <div className="mt-1 line-clamp-2 text-xs leading-5 text-[color:var(--muted)]">
                {entry.description || entry.error_message || "No description yet."}
              </div>
            </button>
          ))
        ) : (
          <div className="px-4 py-6 text-sm text-[color:var(--muted)]">No workflows yet.</div>
        )}
      </div>
    </div>
  );

  const banner = error ? <Banner tone="danger">{error}</Banner> : notice ? <Banner tone="success">{notice}</Banner> : null;

  const save = () =>
    startTransition(async () => {
      try {
        setError("");
        const saved = await sidecar.saveWorkflow(draft);
        setDraft(saved);
        setWorkflowMap((current) => ({ ...current, [saved.id]: saved }));
        setNotice("Workflow saved and published.");
        await reloadEntries();
        setSelectedId(saved.id);
      } catch (event) {
        setNotice("");
        setError(extractMessage(event, "Save failed."));
      }
    });

  const duplicate = () => {
    const now = new Date().toISOString();
    const newId = `${draft.id}-copy`;
    setDraft({
      ...draft,
      id: newId,
      name: `${draft.name} (Copy)`,
      created_at: now,
      updated_at: now,
    });
    setSelectedId("");
    setNotice("Duplicated. Save to publish.");
  };

  const remove = () => {
    if (!selectedId) {
      return;
    }
    const ok = window.confirm(`Delete workflow "${draft.name}"? This removes it from the runtime.`);
    if (!ok) {
      return;
    }
    startTransition(async () => {
      try {
        await sidecar.deleteWorkflow(selectedId);
        await reloadEntries();
        setDraft(createDraft());
        setSelectedId("");
        setNotice("Workflow deleted.");
      } catch (event) {
        setError(extractMessage(event, "Delete failed."));
      }
    });
  };

  return (
    <AppShell sidebar={sidebar} banner={banner}>
      <Panel>
        <PanelHeader
          eyebrow={draft.id}
          title={draft.name || "Untitled workflow"}
          action={
            <>
              <Badge tone={draft.is_active ? "success" : "ghost"}>{draft.is_active ? "active" : "inactive"}</Badge>
              <button type="button" className="btn btn-primary" onClick={save} disabled={isPending}>
                <IconSave size={13} />
                {isPending ? "Saving…" : "Save"}
              </button>
              <button type="button" className="btn" onClick={duplicate}>
                <IconCopy size={13} />
                Duplicate
              </button>
              <button type="button" className="btn" onClick={remove} disabled={!selectedId || isPending} aria-label="Delete workflow">
                <IconTrash size={13} />
                Delete
              </button>
            </>
          }
        />
        <div className="space-y-6 px-5 py-5">
          <section>
            <div className="monoline">Basics</div>
            <div className="mt-3 grid gap-4 md:grid-cols-2">
              <Field label="Workflow Name">
                <input
                  className="w-full"
                  value={draft.name}
                  onChange={(event) => setDraft((current) => ({ ...current, name: event.target.value }))}
                />
              </Field>
              <Field label="Workflow Id" hint="Lowercase slug used for storage and routing.">
                <input
                  className="w-full"
                  value={draft.id}
                  onChange={(event) => setDraft((current) => ({ ...current, id: event.target.value.toLowerCase().replace(/\s+/g, "-") }))}
                />
              </Field>
              <Field label="Description" className="md:col-span-2">
                <textarea
                  className="min-h-[90px] w-full"
                  value={draft.description}
                  onChange={(event) => setDraft((current) => ({ ...current, description: event.target.value }))}
                />
              </Field>
            </div>
            <label className="mt-3 inline-flex items-center gap-2 text-sm text-[color:var(--muted)]">
              <input
                type="checkbox"
                checked={draft.is_active}
                onChange={(event) => setDraft((current) => ({ ...current, is_active: event.target.checked }))}
              />
              Workflow is active in the runtime picker
            </label>
          </section>

          <section>
            <div className="flex items-center justify-between">
              <div className="monoline">Prompt</div>
              <div className="flex items-center gap-3">
                <span className="mono text-[11px] text-[color:var(--subtle)]">{draft.prompt.length} chars</span>
                <button
                  type="button"
                  className="btn btn-ghost px-2 py-1 text-xs"
                  onClick={() => setPromptCollapsed((value) => !value)}
                  aria-expanded={!promptCollapsed}
                >
                  {promptCollapsed ? <IconChevronDown size={12} /> : <IconChevronUp size={12} />}
                  {promptCollapsed ? "expand" : "collapse"}
                </button>
              </div>
            </div>
            {!promptCollapsed ? (
              <textarea
                className="mono mt-3 min-h-[140px] w-full text-[13px] leading-6"
                value={draft.prompt}
                onChange={(event) => setDraft((current) => ({ ...current, prompt: event.target.value }))}
              />
            ) : null}
          </section>

          <SchemaEditor
            title="Inputs"
            rows={draft.input_fields}
            onChange={(rows) => setDraft((current) => ({ ...current, input_fields: rows as InputFieldDefinition[] }))}
            onAdd={() =>
              setDraft((current) => ({
                ...current,
                input_fields: [
                  ...current.input_fields,
                  { id: `input_${current.input_fields.length + 1}`, label: "New Input", type: "short_text", required: false, help_text: "" },
                ],
              }))
            }
            kind="input"
          />
          <SchemaEditor
            title="Structured Outputs"
            rows={draft.output_fields}
            onChange={(rows) => setDraft((current) => ({ ...current, output_fields: rows as OutputFieldDefinition[] }))}
            onAdd={() =>
              setDraft((current) => ({
                ...current,
                output_fields: [
                  ...current.output_fields,
                  { id: `output_${current.output_fields.length + 1}`, label: "New Output", type: "text", required: false, help_text: "" },
                ],
              }))
            }
            kind="output"
          />
          <SchemaEditor
            title="Artifacts"
            rows={draft.artifact_outputs}
            onChange={(rows) => setDraft((current) => ({ ...current, artifact_outputs: rows as ArtifactOutputDefinition[] }))}
            onAdd={() =>
              setDraft((current) => ({
                ...current,
                artifact_outputs: [
                  ...current.artifact_outputs,
                  { id: `artifact_${current.artifact_outputs.length + 1}`, label: "New Artifact", format: "csv", required: false, help_text: "" },
                ],
              }))
            }
            kind="artifact"
          />
        </div>
      </Panel>
    </AppShell>
  );
}

function extractMessage(value: unknown, fallback: string) {
  if (value instanceof Error && value.message) {
    return value.message;
  }
  if (typeof value === "string" && value.trim()) {
    return value;
  }
  if (value && typeof value === "object") {
    const record = value as Record<string, unknown>;
    const message = record.message;
    if (typeof message === "string" && message.trim()) {
      return message;
    }
  }
  return fallback;
}

function SchemaEditor({
  title,
  rows,
  onChange,
  onAdd,
  kind,
}: {
  title: string;
  rows: SchemaRow[];
  onChange: (rows: SchemaRow[]) => void;
  onAdd: () => void;
  kind: "input" | "output" | "artifact";
}) {
  const updateRow = (index: number, patch: Partial<SchemaRow>) => {
    onChange(rows.map((item, itemIndex) => (itemIndex === index ? ({ ...item, ...patch } as SchemaRow) : item)));
  };
  const removeRow = (index: number) => {
    onChange(rows.filter((_, itemIndex) => itemIndex !== index));
  };
  return (
    <section>
      <div className="flex items-center justify-between">
        <div className="monoline">{title}</div>
        <span className="mono text-[11px] text-[color:var(--subtle)]">{rows.length} field{rows.length === 1 ? "" : "s"}</span>
      </div>
      <div className="mt-3 space-y-3">
        {rows.map((row, index) => (
          <div key={index} className="panel-muted space-y-3 p-3">
            <div className="grid gap-2 md:grid-cols-[1fr_1fr_140px_auto]">
              <input
                className="w-full"
                placeholder="label"
                aria-label="Label"
                value={row.label}
                onChange={(event) => updateRow(index, { label: event.target.value })}
              />
              <input
                className="w-full"
                placeholder="id"
                aria-label="Identifier"
                value={row.id}
                onChange={(event) => updateRow(index, { id: event.target.value })}
              />
              {kind === "artifact" ? (
                <select
                  className="w-full"
                  aria-label="Format"
                  value={(row as ArtifactOutputDefinition).format}
                  onChange={(event) => updateRow(index, { format: event.target.value as ArtifactOutputDefinition["format"] })}
                >
                  {["csv", "docx", "xlsx", "pptx", "txt", "md", "json", "html"].map((option) => (
                    <option key={option}>{option}</option>
                  ))}
                </select>
              ) : (
                <select
                  className="w-full"
                  aria-label="Type"
                  value={(row as InputFieldDefinition | OutputFieldDefinition).type}
                  onChange={(event) => updateRow(index, { type: event.target.value as InputFieldDefinition["type"] })}
                >
                  {(kind === "input"
                    ? ["short_text", "long_text", "file"]
                    : ["text", "markdown", "json", "number", "boolean"]
                  ).map((option) => (
                    <option key={option}>{option}</option>
                  ))}
                </select>
              )}
              <div className="flex items-center gap-2">
                <label className="mono inline-flex items-center gap-1.5 border border-[color:var(--line)] bg-white px-2 py-2 text-[11px]">
                  <input
                    type="checkbox"
                    checked={row.required}
                    onChange={(event) => updateRow(index, { required: event.target.checked })}
                  />
                  required
                </label>
                <button
                  type="button"
                  className="btn btn-ghost px-2 py-2"
                  onClick={() => removeRow(index)}
                  aria-label={`Remove ${row.label || "row"}`}
                >
                  <IconTrash size={14} />
                </button>
              </div>
            </div>
            <div>
              <div className="monoline mb-1">Help text</div>
              <input
                className="w-full"
                placeholder="Shown under the field on the runtime form"
                value={row.help_text}
                onChange={(event) => updateRow(index, { help_text: event.target.value })}
              />
            </div>
          </div>
        ))}
      </div>
      <button type="button" className="btn btn-ghost mt-3" onClick={onAdd}>
        <IconPlus size={12} />
        Add {kind === "artifact" ? "artifact" : kind}
      </button>
    </section>
  );
}
