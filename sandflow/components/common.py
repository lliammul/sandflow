from __future__ import annotations

import reflex as rx

FONT_SANS = "'IBM Plex Sans', sans-serif"
FONT_MONO = "'IBM Plex Mono', monospace"

PAGE_BG = "#eef1f3"
SURFACE = "#ffffff"
SURFACE_STRONG = "#f7f9fa"
INK = "#182126"
INK_2 = "#53606b"
INK_3 = "#7b8894"
BORDER = "#253038"
RULE = "#d6dde2"
ACCENT = "#d95c3f"
ACCENT_SOFT = "#fde7dc"
SUCCESS = "#d8e7d8"
SUCCESS_INK = "#2a4a2c"
ERROR = "#f0d3d0"
ERROR_INK = "#8b2722"
INFO = "#dae2ea"
CORNER = "0"
CORNER_SOFT = "3px"

TEXT_XS = "0.72rem"
TEXT_SM = "0.82rem"
TEXT_BASE = "0.9rem"
TEXT_LG = "1.05rem"
TEXT_XL = "1.35rem"


def page_shell(
    *,
    current: str,
    sidebar: rx.Component,
    content: rx.Component,
    banner: rx.Component | None = None,
) -> rx.Component:
    return rx.box(
        rx.container(
            rx.vstack(
                topbar(current=current),
                banner if banner is not None else rx.fragment(),
                rx.flex(
                    rx.box(sidebar, width=rx.breakpoints(initial="100%", lg="240px"), flex_shrink="0"),
                    rx.box(content, width="100%", flex_grow="1", min_width="0"),
                    direction=rx.breakpoints(initial="column", lg="row"),
                    spacing="6",
                    width="100%",
                    align="start",
                ),
                spacing="4",
                width="100%",
                py=rx.breakpoints(initial="0.75rem", md="1rem"),
            ),
            max_width="1280px",
            px=rx.breakpoints(initial="0.75rem", md="1rem", lg="1.25rem"),
        ),
        min_height="100vh",
        bg=PAGE_BG,
        font_family=FONT_SANS,
    )


def topbar(*, current: str) -> rx.Component:
    return rx.hstack(
        rx.text(
            "sandflow",
            color=INK,
            font_weight="700",
            font_size=TEXT_BASE,
            letter_spacing="-0.01em",
        ),
        rx.box(width="1px", height="1.1rem", bg=RULE, mx="0.5rem"),
        rx.hstack(
            nav_link("User", "/", current == "user"),
            nav_link("Builder", "/builder", current == "builder"),
            spacing="1",
            align="center",
        ),
        rx.spacer(),
        rx.box(width="1px", height="1.1rem", bg=RULE, mx="0.5rem"),
        rx.text(
            "Workflow Console",
            color=INK_2,
            font_family=FONT_MONO,
            font_size=TEXT_XS,
            letter_spacing="0.04em",
        ),
        width="100%",
        align="center",
        border=f"1px solid {RULE}",
        bg=SURFACE,
        border_radius=CORNER,
        px="0.85rem",
        py="0.55rem",
    )


def nav_link(label: str, href: str, active: bool) -> rx.Component:
    return rx.link(
        rx.text(
            label,
            color="#fffdf8" if active else INK_2,
            font_weight="600" if active else "500",
            font_size="0.85rem",
        ),
        href=href,
        text_decoration="none",
        bg=INK if active else "transparent",
        border=f"1px solid {INK}" if active else f"1px solid {RULE}",
        border_radius=CORNER,
        px="0.7rem",
        py="0.3rem",
        _hover={} if active else {"bg": SURFACE_STRONG, "border_color": BORDER},
    )


def section_header(
    title: str | rx.Var,
    *,
    meta: rx.Component | None = None,
) -> rx.Component:
    return rx.hstack(
        rx.text(
            title,
            color=INK,
            font_weight="700",
            font_size=TEXT_BASE,
            letter_spacing="-0.005em",
        ),
        rx.spacer(),
        meta if meta is not None else rx.fragment(),
        width="100%",
        align="center",
    )


def panel(
    title: str,
    *children: rx.Component,
    right: rx.Component | None = None,
    chrome: str = "boxed",
) -> rx.Component:
    header = rx.hstack(
        rx.text(
            title,
            font_size="0.88rem",
            font_weight="600",
            color=INK,
        ),
        rx.spacer(),
        right if right is not None else rx.fragment(),
        width="100%",
        align="center",
    )
    inner = rx.vstack(
        header,
        *children,
        spacing="3",
        align="start",
        width="100%",
    )
    if chrome == "bare":
        return rx.box(inner, width="100%")
    return rx.box(
        inner,
        border=f"1px solid {RULE}",
        bg=SURFACE,
        border_radius=CORNER,
        p=rx.breakpoints(initial="0.85rem", md="1rem"),
        width="100%",
    )


def sublabel(text: str) -> rx.Component:
    return rx.text(
        text,
        font_family=FONT_MONO,
        text_transform="uppercase",
        letter_spacing="0.06em",
        font_size="0.68rem",
        color=INK_3,
    )


def helper_text(text) -> rx.Component:
    return rx.text(text, color=INK_2, font_size="0.82rem", line_height="1.55")


def input_shell(
    label_text: str,
    control: rx.Component,
    help_text: str = "",
    *,
    required: bool | rx.Var = False,
) -> rx.Component:
    return rx.vstack(
        rx.hstack(
            rx.text(
                label_text,
                color=INK,
                font_weight="600",
                font_size="0.82rem",
            ),
            rx.cond(
                required,
                rx.text("required", color=ACCENT, font_size="0.7rem", font_weight="600"),
                rx.fragment(),
            ),
            spacing="2",
            align="center",
        ),
        control,
        rx.cond(help_text != "", helper_text(help_text), rx.fragment()),
        spacing="1",
        align="start",
        width="100%",
    )


def pill(text, *, tone="neutral") -> rx.Component:
    bg = rx.match(
        tone,
        ("active", SUCCESS),
        ("success", SUCCESS),
        ("error", ERROR),
        ("accent", ACCENT_SOFT),
        SURFACE_STRONG,
    )
    color = rx.match(
        tone,
        ("active", SUCCESS_INK),
        ("success", SUCCESS_INK),
        ("error", ERROR_INK),
        ("accent", ACCENT),
        INK_2,
    )
    return rx.badge(
        text,
        bg=bg,
        color=color,
        border="none",
        border_radius=CORNER_SOFT,
        px="0.45rem",
        py="0.1rem",
        font_size=TEXT_XS,
        font_weight="600",
    )


def icon(name: str, *, size: int = 14, color: str | None = None, **kwargs) -> rx.Component:
    props = {"tag": name, "size": size, **kwargs}
    if color is not None:
        props["color"] = color
    return rx.icon(**props)


def status_dot(tone: str | rx.Var = "neutral", size: str = "0.42rem") -> rx.Component:
    bg = rx.match(
        tone,
        ("active", SUCCESS_INK),
        ("success", SUCCESS_INK),
        ("error", ERROR_INK),
        ("accent", ACCENT),
        RULE,
    )
    return rx.box(
        width=size,
        height=size,
        bg=bg,
        border_radius="50%",
        flex_shrink="0",
    )


def stepper(steps) -> rx.Component:
    return rx.hstack(
        rx.foreach(steps, _stepper_step),
        spacing="0",
        width="100%",
        align="center",
    )


def _stepper_step(step) -> rx.Component:
    state = step["state"]
    circle_bg = rx.match(
        state,
        ("complete", INK),
        ("active", ACCENT),
        ("failed", ERROR_INK),
        SURFACE,
    )
    circle_border = rx.match(
        state,
        ("complete", INK),
        ("active", ACCENT),
        ("failed", ERROR_INK),
        INK_3,
    )
    circle_border_width = rx.cond(state == "pending", "2px", "1.5px")
    circle_color = rx.cond(state == "pending", INK_3, "#fffdf8")
    label_color = rx.match(
        state,
        ("complete", INK),
        ("active", INK),
        ("failed", ERROR_INK),
        INK_3,
    )
    label_weight = rx.cond(state == "active", "700", "500")
    circle_content = rx.match(
        state,
        ("complete", icon("check", size=12, color="#fffdf8")),
        ("failed", icon("x", size=12, color="#fffdf8")),
        rx.text(
            step["index"],
            color=circle_color,
            font_family=FONT_MONO,
            font_size="0.7rem",
            font_weight="700",
            line_height="1",
        ),
    )
    return rx.hstack(
        rx.vstack(
            rx.box(
                circle_content,
                width="1.6rem",
                height="1.6rem",
                bg=circle_bg,
                border_width=circle_border_width,
                border_style="solid",
                border_color=circle_border,
                border_radius="50%",
                display="flex",
                align_items="center",
                justify_content="center",
                flex_shrink="0",
            ),
            rx.text(
                step["label"],
                color=label_color,
                font_weight=label_weight,
                font_size=TEXT_XS,
                text_align="center",
            ),
            spacing="2",
            align="center",
            flex_shrink="0",
        ),
        rx.cond(
            step["is_last"],
            rx.fragment(),
            rx.box(
                height="2px",
                bg=rx.cond(state == "complete", INK, RULE),
                flex_grow="1",
                min_width="1.5rem",
                mt="-0.65rem",
            ),
        ),
        spacing="2",
        align="center",
        flex_grow=rx.cond(step["is_last"], "0", "1"),
        min_width="0",
    )


def mono_block(text) -> rx.Component:
    return rx.box(
        rx.text(text, white_space="pre-wrap", font_family=FONT_MONO, font_size="0.76rem", color=INK_2, width="100%"),
        width="100%",
        border=f"1px solid {RULE}",
        bg=SURFACE_STRONG,
        border_radius=CORNER,
        p="0.75rem",
    )


def row_actions(*children: rx.Component) -> rx.Component:
    return rx.hstack(*children, spacing="2", wrap="wrap", align="center")


_BUTTON_BASE = dict(
    border_radius=CORNER_SOFT,
    font_size=TEXT_SM,
    cursor="pointer",
)


def primary_button(label, **kwargs) -> rx.Component:
    defaults = {
        **_BUTTON_BASE,
        "bg": ACCENT,
        "color": "#fffdf8",
        "border": f"1px solid {ACCENT}",
        "px": "0.95rem",
        "py": "0.4rem",
        "font_weight": "600",
        "_hover": {"bg": "#c64e34", "border_color": "#c64e34"},
    }
    return rx.button(label, **{**defaults, **kwargs})


def secondary_button(label, **kwargs) -> rx.Component:
    defaults = {
        **_BUTTON_BASE,
        "bg": "transparent",
        "color": INK,
        "border": f"1px solid {RULE}",
        "px": "0.85rem",
        "py": "0.35rem",
        "font_weight": "500",
        "_hover": {"border_color": BORDER, "bg": SURFACE_STRONG},
    }
    return rx.button(label, **{**defaults, **kwargs})


def ghost_button(label, **kwargs) -> rx.Component:
    defaults = {
        **_BUTTON_BASE,
        "bg": "transparent",
        "color": INK_2,
        "border": "1px solid transparent",
        "px": "0.7rem",
        "py": "0.3rem",
        "font_weight": "500",
        "_hover": {"bg": SURFACE_STRONG, "color": INK},
    }
    return rx.button(label, **{**defaults, **kwargs})


def destructive_button(label, **kwargs) -> rx.Component:
    defaults = {
        **_BUTTON_BASE,
        "bg": "transparent",
        "color": ERROR_INK,
        "border": f"1px solid {ERROR}",
        "px": "0.7rem",
        "py": "0.3rem",
        "font_weight": "500",
        "_hover": {"bg": "#fdf0ef", "border_color": ERROR_INK},
    }
    return rx.button(label, **{**defaults, **kwargs})


def link_button(label, **kwargs) -> rx.Component:
    defaults = {
        "bg": "transparent",
        "color": INK_3,
        "border": "none",
        "border_radius": CORNER,
        "px": "0",
        "py": "0",
        "font_size": "0.8rem",
        "font_weight": "500",
        "cursor": "pointer",
        "_hover": {"color": INK, "text_decoration": "underline"},
    }
    return rx.button(label, **{**defaults, **kwargs})


STYLESHEETS = [
    "https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;700&family=IBM+Plex+Sans:wght@400;500;600;700&display=swap",
]
