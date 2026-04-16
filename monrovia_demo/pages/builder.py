from __future__ import annotations

import reflex as rx

from ..components.common import (
    ACCENT,
    ACCENT_SOFT,
    BORDER,
    CORNER,
    ERROR,
    ERROR_INK,
    FONT_MONO,
    INK,
    INK_2,
    INK_3,
    RULE,
    SUCCESS_INK,
    SURFACE,
    SURFACE_STRONG,
    destructive_button,
    ghost_button,
    helper_text,
    mono_block,
    page_shell,
    pill,
    primary_button,
    secondary_button,
    section_header,
    status_dot,
    sublabel,
)
from ..state.builder_state import BuilderState

INPUT_TYPE_OPTIONS = ["short_text", "long_text", "file"]
OUTPUT_TYPE_OPTIONS = ["text", "markdown", "json", "number", "boolean"]
ARTIFACT_FORMAT_OPTIONS = ["csv", "docx", "xlsx", "pptx", "txt", "md", "json", "html"]


def builder_page() -> rx.Component:
    return page_shell(
        current="builder",
        sidebar=workflow_sidebar(),
        content=rx.vstack(
            basics_section(),
            prompt_section(),
            schema_section(
                "Inputs",
                "input",
                BuilderState.input_rows,
                BuilderState.add_input_row,
            ),
            schema_section(
                "Structured Outputs",
                "output",
                BuilderState.output_rows,
                BuilderState.add_output_row,
            ),
            schema_section(
                "Artifacts",
                "artifact",
                BuilderState.artifact_rows,
                BuilderState.add_artifact_row,
            ),
            preview_section(),
            spacing="6",
            width="100%",
        ),
        banner=rx.cond(
            BuilderState.has_invalid_entry,
            invalid_entry_banner(),
            rx.fragment(),
        ),
    )


def invalid_entry_banner() -> rx.Component:
    return rx.box(
        rx.vstack(
            rx.text(
                "This workflow file is invalid and cannot be edited until it is replaced or deleted.",
                color=INK,
                font_weight="600",
                font_size="0.85rem",
            ),
            rx.text(
                BuilderState.invalid_entry_error,
                color=INK_2,
                font_size="0.78rem",
                white_space="pre-wrap",
                font_family=FONT_MONO,
            ),
            spacing="1",
            align="start",
        ),
        bg="#fdf0ef",
        border=f"1px solid {ERROR}",
        border_radius=CORNER,
        px="0.85rem",
        py="0.6rem",
        width="100%",
    )


def workflow_sidebar() -> rx.Component:
    return rx.vstack(
        rx.hstack(
            section_header("Workflows"),
            rx.spacer(),
            ghost_button("+ New", on_click=BuilderState.new_workflow, font_size="0.78rem"),
            width="100%",
            align="center",
        ),
        rx.vstack(
            rx.foreach(BuilderState.workflow_entries, workflow_entry_row),
            spacing="1",
            width="100%",
        ),
        spacing="2",
        align="start",
        width="100%",
    )


def workflow_entry_row(entry: dict) -> rx.Component:
    selected = entry["id"] == BuilderState.selected_registry_id
    dot_tone = rx.cond(
        entry["has_error"],
        "error",
        rx.cond(entry["is_active"], "success", "neutral"),
    )
    return rx.box(
        rx.vstack(
            rx.hstack(
                status_dot(tone=dot_tone),
                rx.text(entry["name"], color=INK, font_weight="600", font_size="0.85rem"),
                rx.spacer(),
                rx.text(entry["id"], font_family=FONT_MONO, color=INK_3, font_size="0.7rem"),
                spacing="2",
                align="center",
                width="100%",
            ),
            rx.cond(
                entry["description"] != "",
                rx.text(
                    entry["description"],
                    color=INK_2,
                    font_size="0.75rem",
                    line_height="1.5",
                ),
                rx.fragment(),
            ),
            spacing="1",
            align="start",
            width="100%",
        ),
        border_left=rx.cond(selected, f"2px solid {ACCENT}", "2px solid transparent"),
        bg=rx.cond(selected, SURFACE_STRONG, "transparent"),
        px="0.7rem",
        py="0.55rem",
        width="100%",
        cursor="pointer",
        on_click=BuilderState.select_workflow(entry["id"]),
        _hover=rx.cond(selected, {}, {"bg": SURFACE_STRONG}),
    )


def basics_section() -> rx.Component:
    return rx.vstack(
        rx.hstack(
            rx.vstack(
                rx.hstack(
                    rx.text(
                        BuilderState.workflow_name,
                        color=INK,
                        font_weight="700",
                        font_size="1.05rem",
                        letter_spacing="-0.01em",
                    ),
                    active_switch(),
                    rx.cond(
                        BuilderState.is_dirty,
                        rx.text("unsaved", color=ACCENT, font_size="0.72rem", font_weight="600"),
                        rx.fragment(),
                    ),
                    spacing="3",
                    align="center",
                ),
                rx.text(
                    BuilderState.workflow_id,
                    color=INK_3,
                    font_family=FONT_MONO,
                    font_size="0.72rem",
                ),
                spacing="1",
                align="start",
            ),
            rx.spacer(),
            rx.hstack(
                primary_button(
                    "Save",
                    on_click=BuilderState.save_current_workflow,
                ),
                secondary_button(
                    "Duplicate",
                    on_click=BuilderState.duplicate_selected_workflow,
                ),
                destructive_button(
                    "Delete",
                    on_click=BuilderState.delete_selected_workflow,
                ),
                spacing="2",
                align="center",
            ),
            width="100%",
            align="start",
        ),
        rx.flex(
            labeled_input(
                "Workflow Name",
                rx.input(
                    value=BuilderState.workflow_name,
                    on_change=BuilderState.infer_slug_from_name,
                    width="100%",
                    bg=SURFACE,
                    border=f"1px solid {RULE}",
                    border_radius=CORNER,
                ),
            ),
            labeled_input(
                "Workflow Id",
                rx.input(
                    value=BuilderState.workflow_id,
                    on_change=BuilderState.set_workflow_id,
                    width="100%",
                    bg=SURFACE,
                    border=f"1px solid {RULE}",
                    border_radius=CORNER,
                ),
                help_text="Lowercase slug used for storage and routing.",
            ),
            spacing="4",
            width="100%",
            direction=rx.breakpoints(initial="column", md="row"),
        ),
        labeled_input(
            "Description",
            rx.text_area(
                value=BuilderState.workflow_description,
                on_change=BuilderState.set_workflow_description,
                width="100%",
                min_height="5rem",
                bg=SURFACE,
                border=f"1px solid {RULE}",
                border_radius=CORNER,
            ),
        ),
        rx.cond(
            BuilderState.editor_notice != "",
            rx.text(BuilderState.editor_notice, color=INK_2, font_size="0.8rem"),
            rx.fragment(),
        ),
        rx.cond(
            BuilderState.has_global_errors,
            rx.box(
                rx.foreach(
                    BuilderState.validation_errors,
                    lambda error: rx.text(error, color=ERROR_INK, font_size="0.82rem", line_height="1.55"),
                ),
                width="100%",
                bg="#fdf0ef",
                border=f"1px solid {ERROR}",
                border_radius=CORNER,
                px="0.85rem",
                py="0.55rem",
            ),
            rx.fragment(),
        ),
        spacing="3",
        align="start",
        width="100%",
    )


def labeled_input(label: str, control: rx.Component, help_text: str = "") -> rx.Component:
    return rx.vstack(
        rx.text(label, color=INK, font_weight="600", font_size="0.8rem"),
        control,
        rx.cond(help_text != "", helper_text(help_text), rx.fragment()),
        spacing="1",
        align="start",
        width="100%",
    )


def active_switch() -> rx.Component:
    label = rx.cond(BuilderState.workflow_active, "active", "inactive")
    tone = rx.cond(BuilderState.workflow_active, "success", "neutral")
    return rx.box(
        rx.hstack(
            status_dot(tone=tone),
            rx.text(label, color=INK_2, font_size="0.75rem", font_weight="500"),
            spacing="1",
            align="center",
        ),
        cursor="pointer",
        on_click=BuilderState.toggle_active,
        border=f"1px solid {RULE}",
        border_radius=CORNER,
        px="0.5rem",
        py="0.2rem",
        _hover={"border_color": BORDER, "bg": SURFACE_STRONG},
    )


def prompt_section() -> rx.Component:
    return rx.vstack(
        rx.hstack(
            section_header(
                "Prompt",
                meta=rx.text(
                    BuilderState.prompt_char_count,
                    color=INK_3,
                    font_family=FONT_MONO,
                    font_size="0.72rem",
                ),
            ),
            rx.spacer(),
            ghost_button(
                rx.cond(BuilderState.prompt_expanded, "collapse", "expand"),
                on_click=BuilderState.toggle_prompt_expanded,
                font_size="0.75rem",
            ),
            width="100%",
            align="center",
        ),
        rx.cond(
            BuilderState.prompt_expanded,
            rx.text_area(
                value=BuilderState.workflow_prompt,
                on_change=BuilderState.set_workflow_prompt,
                width="100%",
                min_height="12rem",
                bg=SURFACE,
                border=f"1px solid {RULE}",
                border_radius=CORNER,
                font_family=FONT_MONO,
                font_size="0.82rem",
            ),
            rx.box(
                rx.text(
                    BuilderState.prompt_preview,
                    color=INK_2,
                    font_family=FONT_MONO,
                    font_size="0.8rem",
                    line_height="1.5",
                ),
                width="100%",
                bg=SURFACE_STRONG,
                border=f"1px solid {RULE}",
                border_radius=CORNER,
                px="0.85rem",
                py="0.55rem",
                cursor="pointer",
                on_click=BuilderState.toggle_prompt_expanded,
                _hover={"border_color": BORDER, "bg": SURFACE},
            ),
        ),
        spacing="2",
        align="start",
        width="100%",
    )


def schema_section(title: str, kind: str, rows, add_event) -> rx.Component:
    return rx.vstack(
        section_header(
            title,
            meta=rx.text(
                rows.length(),
                " fields",
                color=INK_3,
                font_family=FONT_MONO,
                font_size="0.72rem",
            ),
        ),
        rx.cond(
            rows.length() > 0,
            rx.vstack(
                rx.foreach(rows, lambda row: schema_row(row, kind)),
                spacing="0",
                width="100%",
            ),
            rx.fragment(),
        ),
        ghost_button(f"+ Add {kind}", on_click=add_event, font_size="0.8rem"),
        spacing="2",
        align="start",
        width="100%",
    )


def schema_row(row: dict, kind: str) -> rx.Component:
    expanded = ~BuilderState.collapsed_row_keys.contains(row["row_key"])
    errors = row["errors"].to(list[str])
    return rx.box(
        rx.vstack(
            rx.flex(
                rx.box(
                    rx.input(
                        value=row["label"],
                        on_change=lambda value: update_row(kind, row["row_key"], "label", value),
                        placeholder="Label",
                        width="100%",
                        bg=SURFACE,
                        border=f"1px solid {RULE}",
                        border_radius=CORNER,
                        font_size="0.85rem",
                    ),
                    width=rx.breakpoints(initial="100%", lg="32%"),
                ),
                rx.box(
                    rx.input(
                        value=row["field_id"],
                        on_change=lambda value: update_row(kind, row["row_key"], "field_id", value),
                        placeholder="id",
                        width="100%",
                        bg=SURFACE,
                        border=f"1px solid {RULE}",
                        border_radius=CORNER,
                        font_family=FONT_MONO,
                        font_size="0.8rem",
                    ),
                    width=rx.breakpoints(initial="100%", lg="24%"),
                ),
                rx.box(
                    type_select(row, kind),
                    width=rx.breakpoints(initial="100%", lg="18%"),
                ),
                rx.hstack(
                    required_toggle(row, kind),
                    ghost_button(
                        rx.cond(expanded, "−", "…"),
                        on_click=BuilderState.toggle_row_expanded(row["row_key"]),
                        px="0.45rem",
                        font_size="0.9rem",
                    ),
                    destructive_button(
                        "×",
                        on_click=remove_row_event(kind, row["row_key"]),
                        px="0.55rem",
                        font_size="1rem",
                        py="0.2rem",
                    ),
                    spacing="1",
                    align="center",
                ),
                spacing="2",
                width="100%",
                align="center",
                direction=rx.breakpoints(initial="column", lg="row"),
            ),
            rx.cond(
                expanded,
                rx.text_area(
                    value=row["help_text"],
                    on_change=lambda value: update_row(kind, row["row_key"], "help_text", value),
                    placeholder="Help text shown below the field…",
                    width="100%",
                    min_height="3.5rem",
                    bg=SURFACE,
                    border=f"1px solid {RULE}",
                    border_radius=CORNER,
                    font_size="0.82rem",
                ),
                rx.fragment(),
            ),
            rx.cond(
                errors.length() > 0,
                rx.vstack(
                    rx.foreach(
                        errors,
                        lambda msg: rx.hstack(
                            status_dot(tone="error", size="0.35rem"),
                            rx.text(msg, color=ERROR_INK, font_size="0.76rem"),
                            spacing="2",
                            align="center",
                        ),
                    ),
                    spacing="1",
                    align="start",
                    width="100%",
                ),
                rx.fragment(),
            ),
            spacing="2",
            align="start",
            width="100%",
        ),
        width="100%",
        py="0.55rem",
        border_bottom=f"1px solid {RULE}",
    )


def type_select(row: dict, kind: str) -> rx.Component:
    common = dict(
        width="100%",
        bg=SURFACE,
        border=f"1px solid {RULE}",
        border_radius=CORNER,
        font_size="0.82rem",
    )
    if kind == "input":
        return rx.select(
            INPUT_TYPE_OPTIONS,
            value=row["type"],
            on_change=lambda value: BuilderState.update_input_row(row["row_key"], "type", value),
            **common,
        )
    if kind == "output":
        return rx.select(
            OUTPUT_TYPE_OPTIONS,
            value=row["type"],
            on_change=lambda value: BuilderState.update_output_row(row["row_key"], "type", value),
            **common,
        )
    return rx.select(
        ARTIFACT_FORMAT_OPTIONS,
        value=row["format"],
        on_change=lambda value: BuilderState.update_artifact_row(row["row_key"], "format", value),
        **common,
    )


def required_toggle(row: dict, kind: str) -> rx.Component:
    handler = {
        "input": BuilderState.toggle_input_required,
        "output": BuilderState.toggle_output_required,
        "artifact": BuilderState.toggle_artifact_required,
    }[kind]
    return rx.box(
        rx.text(
            rx.cond(row["required"], "required", "optional"),
            color=rx.cond(row["required"], ACCENT, INK_2),
            font_size="0.72rem",
            font_weight="600",
        ),
        bg=rx.cond(row["required"], ACCENT_SOFT, SURFACE_STRONG),
        border=rx.cond(row["required"], f"1px solid {ACCENT}", f"1px solid {RULE}"),
        border_radius=CORNER,
        px="0.55rem",
        py="0.25rem",
        cursor="pointer",
        on_click=handler(row["row_key"]),
        _hover={"border_color": BORDER},
    )


def update_row(kind: str, row_key: str, field: str, value):
    if kind == "input":
        return BuilderState.update_input_row(row_key, field, value)
    if kind == "output":
        return BuilderState.update_output_row(row_key, field, value)
    return BuilderState.update_artifact_row(row_key, field, value)


def remove_row_event(kind: str, row_key: str):
    if kind == "input":
        return BuilderState.remove_input_row(row_key)
    if kind == "output":
        return BuilderState.remove_output_row(row_key)
    return BuilderState.remove_artifact_row(row_key)


def preview_section() -> rx.Component:
    return rx.vstack(
        rx.hstack(
            section_header("Preview"),
            rx.spacer(),
            ghost_button(
                rx.cond(BuilderState.preview_expanded, "hide", "show"),
                on_click=BuilderState.toggle_preview_expanded,
                font_size="0.75rem",
            ),
            width="100%",
            align="center",
        ),
        rx.cond(
            BuilderState.preview_expanded,
            rx.flex(
                rx.vstack(
                    sublabel("Schema"),
                    mono_block(BuilderState.schema_preview),
                    spacing="2",
                    align="start",
                    width="100%",
                ),
                rx.vstack(
                    sublabel("Execution Contract"),
                    mono_block(BuilderState.contract_preview),
                    spacing="2",
                    align="start",
                    width="100%",
                ),
                width="100%",
                spacing="4",
                direction=rx.breakpoints(initial="column", lg="row"),
            ),
            rx.fragment(),
        ),
        spacing="2",
        align="start",
        width="100%",
    )
