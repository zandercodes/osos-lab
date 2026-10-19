# SPDX-License-Identifier: GPL-3.0-only
"""Read UI sources and write generated C resources and headers."""

from .codegen import emit_bindings, emit_header, emit_resources
from .compiler import compile_document
from .parser import read


def page_text(source, page, revision, version):
    text = (source.parent / page.text_file).read_text()
    return build_text(text, revision, version)


def build_text(text, revision, version):
    display = "Development" if version.startswith("0.0.0-dev") else version
    return text.replace("{build_revision}", revision).replace(
        "{build_version}", display
    )


def generate(resources, sources, directory, revision, version="0.0.0-dev"):
    directory.mkdir(parents=True, exist_ok=True)
    lines = [
        '#include "resources.h"',
        '#include "ui.h"',
        '#include "patch.h"',
        '#include "osos.h"',
        "",
    ]
    for source in sources:
        document = read(source)
        text = ""
        if document.root and document.root.kind == "text":
            text = page_text(source, document.root, revision, version)
            document.strings = {
                name: build_text(value, revision, version)
                for name, value in document.strings.items()
            }
            document.translations = {
                name: {
                    language: build_text(value, revision, version)
                    for language, value in variants.items()
                }
                for name, variants in document.translations.items()
            }
        try:
            compiled = compile_document(resources, document, text)
        except ValueError as error:
            raise ValueError(f"{source}: {error}") from error
        if document.root:
            lines.extend(emit_bindings(document, compiled.fields, compiled.actions))
        (directory / (source.stem + "_ui.h")).write_text(
            emit_header(document, compiled.string_ids)
        )
    lines.extend(emit_resources(resources))
    path = directory / "ui_resources.c"
    path.write_text("\n".join(lines))
    return path
