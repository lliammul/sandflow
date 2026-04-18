"use client";

import { useEffect, useMemo, useState, useTransition } from "react";

import { sidecar } from "../lib/sidecar";
import type { ArtifactOutputDefinition, InputFieldDefinition, OutputFieldDefinition, WorkflowDefinition, WorkflowRegistryEntry } from "../lib/types";
import { AppShell } from "./app-shell";
import { Badge, Field, Panel, SectionTitle } from "./shared";

type DraftField = { id: string; label: string; required: boolean; help_text: string; type?: string; format?: string };

function createDraft(): WorkflowDefinition {
  const now = new Date().toISOString();
  return {
    schema_version: 1,
    id: "review-document",
    name: "Review Document",
    description: "Review an uploaded document and produce structured findings plus an optional file artifact.",
    is_active: true,
    prompt:
      "Review the provided document and produce a concise executive summary. Return a JSON array of findings where each item includes severity, title, evidence, and recommendation.",
    input_fields: [{ id: "document", label: "Document", type: "file", required: true, help_text: "" }],
    output_fields: [{ id: "summary", label: "Summary", type: "markdown", required: true, help_text: "" }],
    artifact_outputs: [{ id: "report_file", label: "Report File", format: "docx", required: false, help_text: "" }],
    created_at: now,
    updated_at: now,
  };
}

export function BuilderConsole() {
  const [entries, setEntries] = useState<WorkflowRegistryEntry[]>([]);
  const [draft, setDraft] = useState<WorkflowDefinition>(createDraft);
  const [selectedId, setSelectedId] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [isPending, startTransition] = useTransition();

  useEffect(() => {
    let active = true;
    void (async () => {
      try {
        const items = await sidecar.getWorkflowEntries(true);
        if (!active) {
          return;
        }
        setEntries(items);
        if (items[0] && !items[0].has_error) {
          setSelectedId(items[0].id);
          setDraft(await sidecar.getWorkflow(items[0].id));
        }
      } catch (event) {
        if (!active) {
          return;
        }
        setError(event instanceof Error ? event.message : "Failed to load workflow entries.");
      }
    })();
    return () => {
      active = false;
    };
  }, []);

  const sidebar = (
    <div className="space-y-3">
      <button
        onClick={() => {
          setSelectedId("");
          setDraft(createDraft());
          setNotice("New workflow draft ready.");
        }}
        className="w-full rounded-[22px] bg-[color:var(--ink)] px-4 py-3 text-sm font-semibold text-white"
      >
        New Workflow
      </button>
      {entries.map((entry) => (
        <button
          key={entry.id}
          onClick={async () => {
            setSelectedId(entry.id);
            setNotice("");
            setError("");
            if (entry.has_error) {
              return;
            }
            setDraft(await sidecar.getWorkflow(entry.id));
          }}
          className={`w-full rounded-[22px] border px-4 py-4 text-left ${
            entry.id === selectedId ? "border-[color:var(--accent)] bg-[color:var(--accent-soft)]" : "border-[color:var(--line)] bg-white/60"
          }`}
        >
          <div className="flex items-center justify-between gap-3">
            <div className="text-sm font-semibold">{entry.name}</div>
            <Badge tone={entry.has_error ? "danger" : entry.is_active ? "success" : "neutral"}>
              {entry.has_error ? "invalid" : entry.is_active ? "active" : "inactive"}
            </Badge>
          </div>
          <div className="mt-2 text-sm leading-6 text-[color:var(--muted)]">{entry.description || entry.error_message || "No description yet."}</div>
        </button>
      ))}
    </div>
  );

  return (
    <AppShell
      title="Builder"
      subtitle="Edit workflow schemas directly against the sidecar contract. Saves publish immediately to local storage."
      sidebar={sidebar}
    >
      <Panel>
        <SectionTitle
          eyebrow="Workflow Definition"
          title={draft.name}
          detail="This editor mirrors the current Reflex-era builder behavior, but persists through the new FastAPI sidecar."
          action={
            <div className="flex gap-3">
              <button
                onClick={() =>
                  startTransition(async () => {
                    try {
                      setError("");
                      const saved = await sidecar.saveWorkflow(draft);
                      setDraft(saved);
                      setNotice("Workflow saved and published.");
                      const items = await sidecar.getWorkflowEntries(true);
                      setEntries(items);
                      setSelectedId(saved.id);
                    } catch (event) {
                      setError(event instanceof Error ? event.message : "Save failed.");
                    }
                  })
                }
                className="rounded-full bg-[color:var(--ink)] px-5 py-3 text-sm font-semibold text-white"
              >
                {isPending ? "Saving..." : "Save"}
              </button>
              <button
                onClick={() =>
                  startTransition(async () => {
                    if (!selectedId) {
                      return;
                    }
                    await sidecar.deleteWorkflow(selectedId);
                    setEntries(await sidecar.getWorkflowEntries(true));
                    setDraft(createDraft());
                    setSelectedId("");
                    setNotice("Workflow deleted.");
                  })
                }
                className="rounded-full border border-[color:var(--line)] px-5 py-3 text-sm font-semibold"
              >
                Delete
              </button>
            </div>
          }
        />
        <div className="mt-6 grid gap-4 md:grid-cols-2">
          <Field label="Workflow Name">
            <input
              className="w-full rounded-[18px] border border-[color:var(--line)] bg-white px-4 py-3"
              value={draft.name}
              onChange={(event) => setDraft((current) => ({ ...current, name: event.target.value }))}
            />
          </Field>
          <Field label="Workflow ID">
            <input
              className="w-full rounded-[18px] border border-[color:var(--line)] bg-white px-4 py-3"
              value={draft.id}
              onChange={(event) => setDraft((current) => ({ ...current, id: event.target.value.toLowerCase().replace(/\s+/g, "-") }))}
            />
          </Field>
          <Field label="Description" hint="Appears in the sidebar and runtime header.">
            <textarea
              className="min-h-[110px] w-full rounded-[18px] border border-[color:var(--line)] bg-white px-4 py-3"
              value={draft.description}
              onChange={(event) => setDraft((current) => ({ ...current, description: event.target.value }))}
            />
          </Field>
          <Field label="Builder Prompt">
            <textarea
              className="min-h-[110px] w-full rounded-[18px] border border-[color:var(--line)] bg-white px-4 py-3"
              value={draft.prompt}
              onChange={(event) => setDraft((current) => ({ ...current, prompt: event.target.value }))}
            />
          </Field>
        </div>
        <div className="mt-4 flex items-center gap-3 text-sm text-[color:var(--muted)]">
          <input
            type="checkbox"
            checked={draft.is_active}
            onChange={(event) => setDraft((current) => ({ ...current, is_active: event.target.checked }))}
          />
          Workflow is active in the runtime picker
        </div>
        {notice ? <div className="mt-4 rounded-[20px] bg-[color:var(--success-soft)] px-4 py-3 text-sm text-[color:var(--success)]">{notice}</div> : null}
        {error ? <div className="mt-4 rounded-[20px] bg-[color:var(--danger-soft)] px-4 py-3 text-sm text-[color:var(--danger)]">{error}</div> : null}
      </Panel>
      <Panel>
        <SchemaEditor
          title="Inputs"
          detail="File and text inputs become form controls on the run screen."
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
      </Panel>
      <Panel>
        <SchemaEditor
          title="Structured Outputs"
          detail="These values populate the saved run record and latest result panel."
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
      </Panel>
      <Panel>
        <SchemaEditor
          title="Artifacts"
          detail="Artifact outputs appear as persisted downloadable files after the run completes."
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
      </Panel>
    </AppShell>
  );
}

function SchemaEditor({
  title,
  detail,
  rows,
  onChange,
  onAdd,
  kind,
}: {
  title: string;
  detail: string;
  rows: Array<InputFieldDefinition | OutputFieldDefinition | ArtifactOutputDefinition>;
  onChange: (rows: DraftField[]) => void;
  onAdd: () => void;
  kind: "input" | "output" | "artifact";
}) {
  return (
    <>
      <SectionTitle
        eyebrow="Schema"
        title={title}
        detail={detail}
        action={
          <button onClick={onAdd} className="rounded-full border border-[color:var(--line)] px-4 py-2 text-sm font-semibold">
            Add Row
          </button>
        }
      />
      <div className="mt-5 grid gap-4">
        {rows.map((row, index) => (
          <div key={`${row.id}-${index}`} className="grid gap-4 rounded-[24px] border border-[color:var(--line)] bg-white p-4 md:grid-cols-5">
            <input
              className="rounded-[16px] border border-[color:var(--line)] px-3 py-2"
              placeholder="id"
              value={row.id}
              onChange={(event) => onChange(rows.map((item, itemIndex) => (itemIndex === index ? { ...item, id: event.target.value } : item)) as DraftField[])}
            />
            <input
              className="rounded-[16px] border border-[color:var(--line)] px-3 py-2"
              placeholder="label"
              value={row.label}
              onChange={(event) => onChange(rows.map((item, itemIndex) => (itemIndex === index ? { ...item, label: event.target.value } : item)) as DraftField[])}
            />
            {kind === "artifact" ? (
              <select
                className="rounded-[16px] border border-[color:var(--line)] px-3 py-2"
                value={(row as ArtifactOutputDefinition).format}
                onChange={(event) =>
                  onChange(rows.map((item, itemIndex) => (itemIndex === index ? { ...item, format: event.target.value } : item)) as DraftField[])
                }
              >
                {["csv", "docx", "xlsx", "pptx", "txt", "md", "json", "html"].map((option) => (
                  <option key={option}>{option}</option>
                ))}
              </select>
            ) : (
              <select
                className="rounded-[16px] border border-[color:var(--line)] px-3 py-2"
                value={(row as InputFieldDefinition | OutputFieldDefinition).type}
                onChange={(event) =>
                  onChange(rows.map((item, itemIndex) => (itemIndex === index ? { ...item, type: event.target.value } : item)) as DraftField[])
                }
              >
                {(kind === "input" ? ["short_text", "long_text", "file"] : ["text", "markdown", "json", "number", "boolean"]).map((option) => (
                  <option key={option}>{option}</option>
                ))}
              </select>
            )}
            <input
              className="rounded-[16px] border border-[color:var(--line)] px-3 py-2"
              placeholder="help text"
              value={row.help_text}
              onChange={(event) =>
                onChange(rows.map((item, itemIndex) => (itemIndex === index ? { ...item, help_text: event.target.value } : item)) as DraftField[])
              }
            />
            <label className="flex items-center justify-between rounded-[16px] border border-[color:var(--line)] px-3 py-2 text-sm">
              Required
              <input
                type="checkbox"
                checked={row.required}
                onChange={(event) =>
                  onChange(rows.map((item, itemIndex) => (itemIndex === index ? { ...item, required: event.target.checked } : item)) as DraftField[])
                }
              />
            </label>
          </div>
        ))}
      </div>
    </>
  );
}
