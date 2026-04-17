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
    ghost_button,
    helper_text,
    mono_block,
    page_shell,
    panel,
    pill,
    primary_button,
    section_header,
    status_dot,
    sublabel,
)
from ..state.user_state import UserState


def user_page() -> rx.Component:
    return page_shell(
        current="user",
        sidebar=workflow_sidebar(),
        content=rx.vstack(
            current_workflow_header(),
            inputs_section(),
            action_row(),
            runtime_section(),
            results_section(),
            history_section(),
            spacing="6",
            width="100%",
        ),
        banner=rx.cond(UserState.show_config_warning, config_banner(), rx.fragment()),
    )


def config_banner() -> rx.Component:
    return rx.box(
        rx.hstack(
            status_dot(tone="accent"),
            rx.text(UserState.config_message, color=INK, font_size="0.85rem"),
            spacing="2",
            align="center",
        ),
        bg=ACCENT_SOFT,
        border=f"1px solid {ACCENT}",
        border_radius=CORNER,
        px="0.85rem",
        py="0.55rem",
        width="100%",
    )


def workflow_sidebar() -> rx.Component:
    return rx.vstack(
        section_header("Workflows"),
        rx.cond(
            UserState.has_workflows,
            rx.vstack(rx.foreach(UserState.workflow_cards, workflow_card), spacing="1", width="100%"),
            helper_text("No active workflows yet."),
        ),
        spacing="2",
        align="start",
        width="100%",
    )


def workflow_card(workflow: dict) -> rx.Component:
    selected = workflow["id"] == UserState.selected_workflow_id
    return rx.box(
        rx.vstack(
            rx.hstack(
                rx.text(workflow["name"], color=INK, font_weight="600", font_size="0.88rem"),
                rx.spacer(),
                rx.text(workflow["id"], font_family=FONT_MONO, font_size="0.7rem", color=INK_3),
                width="100%",
                align="center",
            ),
            rx.text(
                workflow["description"],
                color=INK_2,
                font_size="0.78rem",
                line_height="1.5",
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
        cursor=rx.cond(UserState.is_running, "not-allowed", "pointer"),
        opacity=rx.cond(UserState.is_running, "0.58", "1"),
        pointer_events=rx.cond(UserState.is_running, "none", "auto"),
        on_click=UserState.select_workflow(workflow["id"]),
        _hover=rx.cond(selected, {}, {"bg": SURFACE_STRONG}),
    )


def current_workflow_header() -> rx.Component:
    return rx.hstack(
        rx.vstack(
            rx.text(
                UserState.selected_workflow_name,
                color=INK,
                font_weight="700",
                font_size="1.05rem",
                letter_spacing="-0.01em",
            ),
            rx.cond(
                UserState.selected_workflow_description != "",
                rx.text(
                    UserState.selected_workflow_description,
                    color=INK_2,
                    font_size="0.85rem",
                    line_height="1.5",
                ),
                rx.fragment(),
            ),
            spacing="1",
            align="start",
        ),
        rx.spacer(),
        pill(UserState.status_badge_label, tone=UserState.status_badge_tone),
        width="100%",
        align="start",
    )


def inputs_section() -> rx.Component:
    return rx.cond(
        UserState.input_fields.length() > 0,
        rx.vstack(
            rx.foreach(UserState.input_fields, input_block),
            spacing="0",
            width="100%",
        ),
        rx.fragment(),
    )


def input_block(field: dict) -> rx.Component:
    return rx.box(
        rx.vstack(
            rx.hstack(
                rx.text(
                    field["label"],
                    color=INK,
                    font_weight="600",
                    font_size="0.9rem",
                ),
                rx.text(field["id"], font_family=FONT_MONO, font_size="0.7rem", color=INK_3),
                rx.spacer(),
                rx.cond(
                    field["required"],
                    pill("required", tone="accent"),
                    pill("optional", tone="neutral"),
                ),
                spacing="2",
                align="center",
                width="100%",
            ),
            rx.cond(
                field["help_text"] != "",
                helper_text(field["help_text"]),
                rx.fragment(),
            ),
            rx.cond(
                field["type"] == "file",
                render_file_control(field),
                rx.cond(
                    field["type"] == "long_text",
                    rx.text_area(
                        value=field["value"],
                        on_change=lambda value: UserState.update_text_input(field["id"], value),
                        placeholder="Enter text...",
                        width="100%",
                        min_height="6rem",
                        bg=SURFACE,
                        border=f"1px solid {RULE}",
                        border_radius=CORNER,
                        disabled=UserState.is_running,
                    ),
                    rx.input(
                        value=field["value"],
                        on_change=lambda value: UserState.update_text_input(field["id"], value),
                        placeholder="Enter text...",
                        width="100%",
                        bg=SURFACE,
                        border=f"1px solid {RULE}",
                        border_radius=CORNER,
                        disabled=UserState.is_running,
                    ),
                ),
            ),
            spacing="2",
            align="start",
            width="100%",
        ),
        width="100%",
        py="0.85rem",
        border_bottom=f"1px solid {RULE}",
    )


def render_file_control(field: dict) -> rx.Component:
    is_active = field["id"] == UserState.active_file_field_id
    return rx.cond(
        is_active,
        rx.cond(
            field["staged_name"] != "",
            file_upload_staged(field),
            file_upload_empty(),
        ),
        file_slot_inactive(field),
    )


def file_upload_empty() -> rx.Component:
    return rx.upload(
        rx.hstack(
            rx.text(
                "Drop file here or click to browse",
                color=INK_2,
                font_size="0.85rem",
            ),
            rx.spacer(),
            rx.text("select a file", color=INK_3, font_size="0.75rem"),
            width="100%",
            align="center",
        ),
        id="shared_file_upload",
        max_files=1,
        on_drop=UserState.handle_active_file_upload,
        width="100%",
        border=f"1px dashed {RULE}",
        border_radius=CORNER,
        bg=SURFACE,
        px="0.85rem",
        py="0.7rem",
        pointer_events=rx.cond(UserState.is_running, "none", "auto"),
        opacity=rx.cond(UserState.is_running, "0.52", "1"),
        _hover={"border_color": ACCENT, "bg": SURFACE_STRONG},
    )


def file_upload_staged(field: dict) -> rx.Component:
    return rx.upload(
        rx.vstack(
            rx.hstack(
                rx.text(
                    field["staged_name"],
                    color=INK,
                    font_family=FONT_MONO,
                    font_size="0.8rem",
                    font_weight="600",
                ),
                pill("staged", tone="success"),
                rx.spacer(),
                rx.text("drop or click to replace", color=INK_3, font_size="0.72rem"),
                spacing="2",
                align="center",
                width="100%",
            ),
            rx.cond(
                field["preview"] != "",
                rx.text(
                    field["preview"],
                    color=INK_2,
                    font_size="0.78rem",
                    line_height="1.5",
                    white_space="pre-wrap",
                ),
                rx.fragment(),
            ),
            spacing="2",
            align="start",
            width="100%",
        ),
        id="shared_file_upload",
        max_files=1,
        on_drop=UserState.handle_active_file_upload,
        width="100%",
        border=f"1px solid {RULE}",
        border_radius=CORNER,
        bg=SURFACE,
        px="0.85rem",
        py="0.7rem",
        pointer_events=rx.cond(UserState.is_running, "none", "auto"),
        opacity=rx.cond(UserState.is_running, "0.52", "1"),
        _hover={"border_color": BORDER},
    )


def file_slot_inactive(field: dict) -> rx.Component:
    return rx.box(
        rx.hstack(
            rx.cond(
                field["staged_name"] != "",
                rx.text(field["staged_name"], color=INK, font_family=FONT_MONO, font_size="0.8rem"),
                rx.text("No file", color=INK_3, font_size="0.82rem"),
            ),
            rx.spacer(),
            rx.text("click to use this slot", color=INK_3, font_size="0.72rem"),
            width="100%",
            align="center",
        ),
        width="100%",
        border=f"1px solid {RULE}",
        bg=SURFACE_STRONG,
        border_radius=CORNER,
        px="0.85rem",
        py="0.55rem",
        cursor="pointer",
        opacity=rx.cond(UserState.is_running, "0.6", "1"),
        on_click=UserState.set_active_file_field(field["id"]),
        _hover={"bg": SURFACE, "border_color": BORDER},
    )


def action_row() -> rx.Component:
    return rx.hstack(
        primary_button(
            "Run Workflow",
            on_click=UserState.run_selected_workflow,
            disabled=~UserState.can_run,
            opacity=rx.cond(UserState.can_run, "1", "0.55"),
        ),
        ghost_button(
            UserState.debug_mode_label,
            on_click=UserState.toggle_debug_mode,
            disabled=UserState.is_running,
        ),
        ghost_button(
            "Clear",
            on_click=UserState.clear_inputs,
            disabled=UserState.is_running,
        ),
        rx.spacer(),
        rx.cond(
            UserState.has_error,
            rx.fragment(),
            rx.fragment(),
        ),
        width="100%",
        align="center",
    )


def runtime_section() -> rx.Component:
    return rx.vstack(
        rx.cond(
            UserState.has_error,
            rx.box(
                rx.text(
                    UserState.error_message,
                    color=ERROR_INK,
                    line_height="1.55",
                    font_size="0.85rem",
                    white_space="pre-wrap",
                ),
                width="100%",
                border=f"1px solid {ERROR}",
                bg="#fdf0ef",
                border_radius=CORNER,
                p="0.7rem",
            ),
            rx.fragment(),
        ),
        section_header(
            "Runtime",
            meta=rx.text(
                UserState.current_stage_label,
                color=INK_3,
                font_family=FONT_MONO,
                font_size="0.72rem",
            ),
        ),
        rx.hstack(
            rx.foreach(UserState.stage_timeline, stage_step),
            spacing="0",
            width="100%",
            align="center",
            wrap="wrap",
        ),
        rx.cond(
            UserState.has_progress,
            rx.vstack(
                rx.foreach(UserState.progress_feed, progress_event_card),
                spacing="0",
                width="100%",
                mt="0.3rem",
            ),
            rx.fragment(),
        ),
        spacing="3",
        align="start",
        width="100%",
    )


def stage_step(step: dict) -> rx.Component:
    dot_bg = rx.match(
        step["state"],
        ("complete", INK),
        ("active", ACCENT),
        ("failed", ERROR_INK),
        "transparent",
    )
    dot_border = rx.match(
        step["state"],
        ("complete", INK),
        ("active", ACCENT),
        ("failed", ERROR_INK),
        RULE,
    )
    return rx.hstack(
        rx.box(
            width="0.55rem",
            height="0.55rem",
            border_radius="50%",
            bg=dot_bg,
            border=rx.cond(step["state"] == "pending", f"1.5px solid {dot_border}", f"1.5px solid {dot_border}"),
            flex_shrink="0",
        ),
        rx.text(
            step["label"],
            color=rx.cond(step["state"] == "pending", INK_3, INK),
            font_weight=rx.cond(step["state"] == "active", "700", "500"),
            font_size="0.78rem",
        ),
        rx.box(
            height="1px",
            bg=RULE,
            flex_grow="1",
            min_width="1rem",
        ),
        spacing="2",
        align="center",
        flex_grow="1",
        min_width="0",
    )


def progress_event_card(event: dict) -> rx.Component:
    return rx.hstack(
        rx.text(
            event["timestamp_label"],
            color=INK_3,
            font_family=FONT_MONO,
            font_size="0.72rem",
            flex_shrink="0",
            width="3.5rem",
        ),
        rx.vstack(
            rx.hstack(
                rx.text(event["title"], color=INK, font_weight="600", font_size="0.83rem"),
                pill(
                    event["kind_label"],
                    tone=rx.cond(
                        event["kind"] == "error",
                        "error",
                        rx.cond(event["kind"] == "stage", "accent", "neutral"),
                    ),
                ),
                spacing="2",
                align="center",
            ),
            rx.cond(
                event["detail"] != "",
                rx.text(event["detail"], color=INK_2, font_size="0.8rem", line_height="1.5"),
                rx.fragment(),
            ),
            spacing="1",
            align="start",
            width="100%",
        ),
        rx.spacer(),
        rx.text(event["stage_label"], color=INK_3, font_family=FONT_MONO, font_size="0.72rem"),
        width="100%",
        align="start",
        border_bottom=f"1px solid {RULE}",
        py="0.55rem",
    )


def results_section() -> rx.Component:
    return rx.cond(
        UserState.has_results,
        rx.vstack(
            section_header("Results"),
            rx.box(
                sublabel("Summary"),
                rx.text(
                    UserState.result_summary,
                    color=INK_2,
                    line_height="1.6",
                    mt="0.3rem",
                    font_size="0.88rem",
                ),
                width="100%",
            ),
            rx.flex(
                rx.box(
                    sublabel("Structured Outputs"),
                    rx.vstack(
                        rx.foreach(UserState.result_fields, result_field_card),
                        spacing="2",
                        width="100%",
                        mt="0.4rem",
                    ),
                    width=rx.breakpoints(initial="100%", lg="62%"),
                ),
                rx.box(
                    sublabel("Artifacts"),
                    rx.vstack(
                        rx.foreach(UserState.result_artifacts, artifact_row),
                        spacing="2",
                        width="100%",
                        mt="0.4rem",
                    ),
                    width=rx.breakpoints(initial="100%", lg="38%"),
                ),
                direction=rx.breakpoints(initial="column", lg="row"),
                spacing="4",
                width="100%",
            ),
            spacing="3",
            align="start",
            width="100%",
        ),
        rx.fragment(),
    )


def result_field_card(field: dict) -> rx.Component:
    return rx.box(
        rx.vstack(
            rx.hstack(
                rx.text(field["label"], color=INK, font_weight="600", font_size="0.82rem"),
                rx.spacer(),
                pill(field["type"], tone="neutral"),
                width="100%",
                align="center",
            ),
            rx.cond(
                field["type"] == "markdown",
                rx.markdown(field["display"]),
                rx.cond(
                    field["type"] == "json",
                    mono_block(field["display"]),
                    rx.text(field["display"], color=INK_2, line_height="1.55", font_size="0.85rem"),
                ),
            ),
            spacing="2",
            align="start",
            width="100%",
        ),
        width="100%",
        border=f"1px solid {RULE}",
        bg=SURFACE,
        border_radius=CORNER,
        p="0.7rem",
    )


def artifact_row(artifact: dict) -> rx.Component:
    return rx.hstack(
        rx.vstack(
            rx.hstack(
                rx.text(artifact["label"], color=INK, font_weight="600", font_size="0.82rem"),
                pill(artifact["format"], tone="neutral"),
                spacing="2",
                align="center",
            ),
            rx.text(artifact["filename"], color=INK_3, font_family=FONT_MONO, font_size="0.72rem"),
            spacing="1",
            align="start",
        ),
        rx.spacer(),
        primary_button(
            "Download",
            on_click=UserState.download_artifact(
                artifact["stored_path"],
                artifact["filename"],
                artifact["mime_type"],
            ),
            font_size="0.78rem",
            px="0.7rem",
            py="0.3rem",
        ),
        width="100%",
        align="center",
        border=f"1px solid {RULE}",
        bg=SURFACE,
        border_radius=CORNER,
        px="0.7rem",
        py="0.55rem",
    )


def history_section() -> rx.Component:
    return rx.vstack(
        section_header(
            "Run History",
            meta=rx.text(
                UserState.runs.length(),
                " runs",
                color=INK_3,
                font_family=FONT_MONO,
                font_size="0.72rem",
            ),
        ),
        rx.cond(
            UserState.runs.length() > 0,
            rx.vstack(rx.foreach(UserState.runs, run_row), spacing="0", width="100%"),
            helper_text("No runs recorded yet."),
        ),
        spacing="2",
        align="start",
        width="100%",
    )


def run_row(run: dict) -> rx.Component:
    expanded = UserState.expanded_run_id == run["id"]
    return rx.box(
        rx.vstack(
            rx.hstack(
                status_dot(tone=rx.cond(run["status"] == "complete", "success", "error")),
                rx.text(run["workflow_name"], color=INK, font_weight="600", font_size="0.85rem"),
                pill(
                    run["status"],
                    tone=rx.cond(run["status"] == "complete", "success", "error"),
                ),
                rx.spacer(),
                rx.text(
                    run["started_label"],
                    color=INK_3,
                    font_family=FONT_MONO,
                    font_size="0.72rem",
                ),
                rx.text(
                    run["stage_count"],
                    " stages · ",
                    run["artifact_count"],
                    " artifacts · ",
                    run["debug_event_count"],
                    " trace",
                    color=INK_3,
                    font_family=FONT_MONO,
                    font_size="0.72rem",
                ),
                spacing="2",
                align="center",
                width="100%",
            ),
            rx.cond(
                expanded,
                rx.vstack(
                    rx.cond(
                        run["summary"] != "",
                        rx.text(
                            run["summary"],
                            color=INK_2,
                            font_size="0.82rem",
                            line_height="1.55",
                        ),
                        rx.fragment(),
                    ),
                    rx.cond(
                        run["error"] != "",
                        rx.box(
                            rx.text(
                                run["error"],
                                color=ERROR_INK,
                                font_size="0.78rem",
                                line_height="1.55",
                                font_family=FONT_MONO,
                                white_space="pre-wrap",
                            ),
                            bg="#fdf0ef",
                            border=f"1px solid {ERROR}",
                            border_radius=CORNER,
                            p="0.65rem",
                            width="100%",
                            max_height="14rem",
                            overflow="auto",
                        ),
                        rx.fragment(),
                    ),
                    rx.box(
                        sublabel("Timeline"),
                        mono_block(run["timeline_text"]),
                        width="100%",
                    ),
                    rx.cond(
                        run["raw_result_json"] != "",
                        rx.box(
                            sublabel("Raw Result"),
                            mono_block(run["raw_result_json"]),
                            width="100%",
                        ),
                        rx.fragment(),
                    ),
                    rx.cond(
                        run["debug_enabled"],
                        rx.box(
                            sublabel("Debug Trace"),
                            mono_block(run["debug_trace_text"]),
                            width="100%",
                        ),
                        rx.fragment(),
                    ),
                    spacing="2",
                    align="start",
                    width="100%",
                    mt="0.4rem",
                ),
                rx.cond(
                    run["preview"] != "",
                    rx.text(
                        run["preview"],
                        color=INK_3,
                        font_size="0.78rem",
                        line_height="1.5",
                        mt="0.15rem",
                    ),
                    rx.fragment(),
                ),
            ),
            spacing="0",
            align="start",
            width="100%",
        ),
        width="100%",
        py="0.6rem",
        border_bottom=f"1px solid {RULE}",
        cursor="pointer",
        on_click=UserState.toggle_run_expanded(run["id"]),
        _hover={"bg": SURFACE_STRONG},
    )
