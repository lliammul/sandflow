import reflex as rx


config = rx.Config(
    app_name="monrovia_demo",
    plugins=[
        rx.plugins.SitemapPlugin(),
        rx.plugins.TailwindV4Plugin(),
    ],
)

