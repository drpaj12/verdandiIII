"""Sphinx configuration of the Verdandi III user manual.

Build: ``sphinx-build -W -b html docs/user build/docs`` (the Pages workflow's command). Every
command, flag and key in the page was checked against verdandi/cli.py, verdandi/odin3/record.py,
verdandi/odin3/abcsteps.py, verdandi/notes.py and verdandi/gui/mainwindow.py. The page needs no
Verdandi, Odin III or PySide6 install to build.
"""

project = "Verdandi III"
author = "Verdandi III contributors"
copyright = "Verdandi III contributors"

extensions = ["myst_parser"]
source_suffix = {".md": "markdown"}
root_doc = "index"
exclude_patterns = ["_build"]
myst_enable_extensions = ["colon_fence"]
myst_heading_anchors = 3
html_theme = "alabaster"

# Shared Yggdrasil III look: the "Manuals" block (hub link on top, links to every manual) leads
# the sidebar on every page. Keep _templates/manuals.html identical across the four manuals.
templates_path = ["_templates"]
html_sidebars = {
    "**": ["manuals.html", "about.html", "navigation.html", "relations.html", "searchbox.html"],
}
