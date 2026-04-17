from __future__ import annotations

import reflex as rx

from .components.common import STYLESHEETS
from .pages.builder import builder_page
from .pages.user import user_page
from .state.builder_state import BuilderState
from .state.user_state import UserState

app = rx.App(
    theme=rx.theme(appearance="light"),
    stylesheets=STYLESHEETS,
)
app.add_page(user_page, route="/", title="sandflow User Console", on_load=UserState.load_page)
app.add_page(
    builder_page,
    route="/builder",
    title="sandflow Builder Console",
    on_load=BuilderState.load_page,
)
