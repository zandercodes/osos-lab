# SPDX-License-Identifier: GPL-3.0-only
"""Offline UI declaration contracts."""

import json
import struct
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from patching.ui import parser
from patching.ui.codegen import emit_header, emit_resources
from patching.ui.compiler import DocumentCompiler, compile_document
from patching.ui.generator import generate
from patching.ui.model import ScreenEvent
from patching.ui.resources import (
    Resources,
    blocks,
    event,
    pack_blocks,
    word,
)

LEGAL_ITEM = 100
MAIN_SCREEN = 101


def selector(name, slot, default=0, values="choices"):
    return (
        f'<selector id="{name}" title="{name}" values="{values}" '
        f'slot="{slot}" default="{default}"/>'
    )


def menu(rows):
    return (
        '<ui><values id="choices">'
        '<value number="0" label="Off"/><value number="1" label="On"/>'
        '</values><menu id="TEST" title="Test">' + "".join(rows) + "</menu></ui>"
    )


class UiTests(unittest.TestCase):
    def test_song_info_loads_catalog_and_generates_format_signatures(self):
        root = Path(__file__).resolve().parents[2]
        metadata = json.loads((root / "firmware/ui.json").read_text())
        bindings = json.loads((root / "payload/native/ui.json").read_text())["bindings"]
        document = parser.read(root / "payload/song_info.ui")
        self.assertEqual(
            document.text(document.root.title).translations[4], "Titelinformationen"
        )
        shared_formats = {
            "CFW_SONG_NUMBER",
            "CFW_SONG_TIME",
            "CFW_SONG_TIME_HOURS",
            "CFW_SONG_KBPS",
            "CFW_SONG_STARS",
        }
        for name in set(document.strings) - shared_formats:
            with self.subTest(string=name):
                self.assertEqual(set(document.translations[name]), set(range(1, 21)))
        resources = Resources(metadata["resources"], bindings)
        compiled = compile_document(resources, document)
        for name, signature in document.formats.items():
            self.assertEqual(resources.formats[compiled.string_ids[name]], signature)
        for item in document.root.items:
            self.assertNotIn(
                (compiled.string_ids[item.name], 4), resources.translations
            )
        self.assertIn('"uu"', "\n".join(emit_resources(resources)))
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "bad.ui"
            source.write_text("<ui/>")
            source.with_suffix(".lo").write_text(
                '<locale><format id="BAD" text="%n"/></locale>'
            )
            with self.assertRaisesRegex(ValueError, "bad.lo"):
                parser.read(source)

    def test_locale_formats_validate_types_and_allow_reordered_arguments(self):
        document = parser.parse(
            '<ui><string id="NAME" text="Name"/></ui>',
            '<locale><format id="ROW" text="%1$s: %2$u%%"/>'
            '<format id="ROW" lang="4" text="%2$u%% - %1$s %1$s"/></locale>',
        )
        self.assertEqual(document.formats, {"ROW": "su"})
        self.assertEqual(parser.format_signature("%s: %u"), "su")
        for text in ("%", "%d", "%n", "%0$s", "%9$s", "%2$s", "%1$s %1$u", "%s %2$u"):
            with self.subTest(text=text), self.assertRaises(ValueError):
                parser.format_signature(text)
        with self.assertRaisesRegex(ValueError, "Mismatched"):
            parser.parse(
                '<ui><format id="ROW" text="%s"/>'
                '<format id="ROW" lang="4" text="%u"/></ui>'
            )
        with self.assertRaises(ValueError):
            parser.parse(
                '<ui><string id="ROW" text="Row"/></ui>',
                '<locale><string id="ROW" text="Other"/></locale>',
            )

    def test_all_payload_documents_generate_together_with_translated_examples(self):
        root = Path(__file__).resolve().parents[2]
        metadata = json.loads((root / "firmware/ui.json").read_text())
        bindings = json.loads((root / "payload/native/ui.json").read_text())["bindings"]
        resources = Resources(metadata["resources"], bindings)
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            result = generate(
                resources,
                sorted((root / "payload").glob("*.ui")),
                directory,
                "test-revision",
                "1.2.3",
            )
            self.assertIn("cfw_translations[]", result.read_text())
            self.assertTrue((directory / "cfw_info_ui.h").exists())
        defaults = [
            bytes(data.data)
            for (kind, _), data in resources.added.items()
            if kind == "Str "
        ]
        translations = list(resources.translations.values())
        self.assertIn(b"Dark Mode\0", defaults)
        self.assertIn(b"Dunkler Modus\0", translations)
        self.assertIn(b"RepriseOS 1.2.3\0", defaults)
        self.assertIn(b"Build: test-revision\0", defaults)
        self.assertIn(b"Custom firmware for iPod.\0", defaults)
        self.assertIn(b"Project:\nhttps://github.com/lgreitis/osos-lab\0", defaults)
        self.assertIn(b"CFW-Informationen\0", translations)
        info = parser.read(root / "payload/cfw_info.ui")
        self.assertEqual(set(info.strings), {"CFW_Info_Title"})
        self.assertFalse(any(data.startswith(b"@CFW_Info") for data in defaults))

    def test_text_page_variants_expand_build_placeholders_and_keep_literal_strings(
        self,
    ):
        root = Path(__file__).resolve().parents[2]
        metadata = json.loads((root / "firmware/ui.json").read_text())
        bindings = json.loads((root / "payload/native/ui.json").read_text())["bindings"]
        resources = Resources(metadata["resources"], bindings)
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            source = directory / "page.ui"
            source.write_text(
                '<ui><text id="PAGE" title="@TITLE" file="@body.txt"/>'
                '<string id="TITLE" text="Page"/>'
                '<string id="TITLE" lang="4" text="Seite"/>'
                '<string id="BODY" text="Version {build_version}"/>'
                '<string id="BODY" lang="4" text="Build {build_revision}&#10;@literal"/>'
                "</ui>"
            )
            (directory / "@body.txt").write_text("@BODY\n\n@@literal")
            generate(resources, [source], directory / "generated", "abc123")
        defaults = [
            bytes(data.data)
            for (kind, _), data in resources.added.items()
            if kind == "Str "
        ]
        self.assertIn(b"Version Development\0", defaults)
        self.assertIn(b"@literal\0", defaults)
        self.assertIn(b"Build abc123\n@literal\0", resources.translations.values())
        self.assertIn(b"Seite\0", resources.translations.values())

    def test_music_title_references_and_empty_translation_codegen(self):
        root = Path(__file__).resolve().parents[2]
        metadata = json.loads((root / "firmware/ui.json").read_text())
        bindings = json.loads((root / "payload/native/ui.json").read_text())["bindings"]
        resources = Resources(metadata["resources"], bindings)
        document = parser.read(root / "payload/album_artists.ui")
        document.music_entry["title"] = "@TITLE"
        document.strings["TITLE"] = "Album Artists"
        document.translations["TITLE"] = {4: "Albuminterpreten"}
        compiled = compile_document(resources, document)
        self.assertEqual(
            resources.translations[compiled.string_ids["CFW_AlbumArtists_Title"], 4],
            b"Albuminterpreten\0",
        )
        output = "\n".join(emit_resources(Resources([])))
        self.assertIn("cfw_translation_count = 0;", output)
        self.assertIn("{0, 0, 0},", output)

    def test_references_compose_with_independent_language_fallbacks(self):
        root = Path(__file__).resolve().parents[2]
        metadata = json.loads((root / "firmware/ui.json").read_text())
        bindings = json.loads((root / "payload/native/ui.json").read_text())["bindings"]
        resources = Resources(metadata["resources"], bindings)
        document = parser.parse(
            '<ui><values id="choices"><value number="0" label="@OFF"/></values>'
            '<range id="levels" first="0" last="1" step="1" suffix="@UNIT"/>'
            '<menu id="TEST" title="@TITLE">'
            '<selector id="STATE" title="@TITLE" values="choices" slot="0" default="0"/>'
            '<selector id="LEVEL" title="Level" values="levels" slot="1" default="0"/>'
            '<info id="INFO" title="@TITLE" unknown="@OFF"/>'
            '<action id="SAVE" title="@TITLE" values="choices"/></menu>'
            '<string id="TITLE" text="State"/><string id="TITLE" lang="4" text="Status"/>'
            '<string id="OFF" text="Off"/><string id="OFF" lang="2" text="Non"/>'
            '<string id="UNIT" text=" units"/><string id="UNIT" lang="4" text=" Einheiten"/>'
            "</ui>"
        )
        compiled = compile_document(resources, document)

        def string_id(source):
            return word(blocks(resources.added["SORC", source])[0][1], 4)

        summary = string_id(compiled.fields[0].summaries[0])
        self.assertEqual(bytes(resources.added["Str ", summary].data), b"State: Off\0")
        self.assertEqual(resources.translations[summary, 4], b"Status: Off\0")
        self.assertEqual(resources.translations[summary, 2], b"State: Non\0")
        marked = string_id(compiled.fields[0].marked[0])
        self.assertEqual(resources.translations[marked, 2], b"Non *\0")
        unit = string_id(compiled.fields[1].labels[0])
        self.assertEqual(resources.translations[unit, 4], b"0 Einheiten\0")
        self.assertEqual(
            resources.translations[compiled.string_ids["INFO"], 4], b"Status: Off\0"
        )
        self.assertEqual(document.text("@@literal").default, "@literal")
        self.assertEqual(document.text("literal").default, "literal")
        with self.assertRaisesRegex(ValueError, "Undefined UI string"):
            document.text("@MISSING")
        with self.assertRaisesRegex(ValueError, "Undefined UI string"):
            parser.parse('<ui><string id="OTHER" text="x"/></ui>').text("@TITLE")

    def test_string_languages_require_unique_variants_and_default(self):
        document = parser.parse(
            '<ui><string id="TITLE" lang="4" text="Deutsch"/>'
            '<string id="TITLE" text="English"/></ui>'
        )
        self.assertEqual(document.strings, {"TITLE": "English"})
        self.assertEqual(document.translations, {"TITLE": {4: "Deutsch"}})
        for declarations in (
            '<string id="TITLE" lang="4" text="Deutsch"/>',
            '<string id="TITLE" text="A"/><string id="TITLE" text="B"/>',
            '<string id="TITLE" text="A"/><string id="TITLE" lang="21" text="B"/>',
            '<string id="TITLE" text="A"/><string id="TITLE" lang="-1" text="B"/>',
            '<string id="TITLE" text="A"/><string id="title" text="B"/>',
            '<string id="TITLE" text="A"/><string id="TITLE" lang="4" text="B"/>'
            '<string id="TITLE" lang="4" text="C"/>',
        ):
            with self.subTest(declarations=declarations), self.assertRaises(ValueError):
                parser.parse("<ui>" + declarations + "</ui>")

    def test_settings_toggle_preserves_stock_rows_and_has_no_navigation(self):
        root = Path(__file__).resolve().parents[2]
        metadata = json.loads((root / "firmware/ui.json").read_text())
        bindings = json.loads((root / "payload/native/ui.json").read_text())["bindings"]
        resources = Resources(metadata["resources"], bindings)
        document = parser.read(root / "payload/dark_mode.ui")
        compiled = compile_document(resources, document)
        stock = blocks(resources.stock("ITEM", "SettingsMenu_Items"))
        rows = blocks(resources.added["ITEM", bindings["SettingsMenu_Items"]])
        anchor = next(
            i
            for i, (_, row) in enumerate(rows)
            if word(row, 0x30) == bindings["SettingsMenu_ListItem_Brightness"]
        )
        _, toggle = rows.pop(anchor + 1)
        for (_, before), (_, after) in zip(stock, rows, strict=True):
            self.assertEqual(before.data, after.data)
            self.assertEqual(before.origins, after.origins)
        prototype = next(
            row
            for _, row in stock
            if word(row, 0x30) == bindings["SettingsMenu_ListItem_SoundCheck"]
        )
        for start, end in ((0, 0x30), (0x34, 0x68), (0x6C, 0x98)):
            self.assertEqual(toggle[start:end].origins, prototype[start:end].origins)
            self.assertEqual(toggle[start:end].data, prototype[start:end].data)
        sources = blocks(resources.added["SORC", word(toggle, 0x68)])
        self.assertEqual(
            [word(sources[1][1], offset) for offset in (0, 4, 8)],
            [0x8900, compiled.string_ids["CFW_DarkMode_Value"], 10],
        )
        events = resources.added["CEVT", bindings["SettingsMenus_Main_Screen"]]
        original = resources.stock("CEVT", "SettingsMenus_Main_Screen")
        appended = bytes(events.data[len(original) :])
        self.assertIn(b"CFW_DarkMode_Toggle", appended)
        self.assertNotIn(b"navigator.PushScreen", appended)
        self.assertNotIn("CFW_DarkMode_Screen", resources.names)

    def test_album_artists_reuses_native_routes_and_adds_a_music_row(self):
        root = Path(__file__).resolve().parents[2]
        metadata = json.loads((root / "firmware/ui.json").read_text())
        shim = root / "payload/native"
        bindings = json.loads((shim / "ui.json").read_text())["bindings"]
        resources = Resources(metadata["resources"], bindings)
        document = parser.read(root / "payload/album_artists.ui")
        compiled = compile_document(resources, document)
        rows = blocks(resources.added["ITEM", bindings["MusicMenu_Items"]])
        self.assertEqual(len(rows), 13)
        anchor = next(
            i
            for i, (_, row) in enumerate(rows)
            if word(row, 0x30) == bindings["MusicMenu_ListItem_Artists"]
        )
        new_row = rows[anchor + 1][1]
        item = word(new_row, 0x30)
        self.assertNotEqual(item, bindings["MusicMenu_ListItem_Artists"])
        self.assertEqual(word(new_row, 0x60), 5)
        self.assertEqual(word(new_row, 0x64) & 0xFF, 1)
        events = resources.added["CEVT", bindings["MainMenus_Music_Screen"]]
        self.assertIn(f"list.pid.{item}.chosen".encode(), events.data)
        self.assertIn(b"CFW_AlbumArtists", events.data)
        self.assertIn(b"HandleMusicHilited", events.data)
        main_rows = blocks(resources.added["ITEM", bindings["MainMenu_Items"]])
        main_anchor = next(
            i
            for i, (_, row) in enumerate(main_rows)
            if word(row, 0x30) == bindings["MainMenu_List_Artists"]
        )
        main_row = main_rows[main_anchor + 1][1]
        main_item = compiled.string_ids["CFW_AlbumArtists_MainItem"]
        self.assertEqual(word(main_row, 0x30), main_item)
        self.assertNotEqual(main_item, item)
        self.assertEqual(word(main_row, 0x64) & 0xFF, 0)
        self.assertEqual(word(main_row, 0x68), word(new_row, 0x68))
        main_events = resources.added["CEVT", bindings["MainMenus_Main_Screen"]]
        self.assertIn(f"list.pid.{main_item}.chosen".encode(), main_events.data)
        self.assertIn(b"CFW_AlbumArtists", main_events.data)
        for table, inserted in (
            ("MainMenu_Items", main_anchor + 1),
            ("MusicMenu_Items", anchor + 1),
        ):
            stock = blocks(resources.stock("ITEM", table))
            updated = blocks(resources.added["ITEM", bindings[table]])
            del updated[inserted]
            self.assertEqual(len(stock), len(updated))
            for (_, before), (_, after) in zip(stock, updated):
                self.assertEqual(before.data, after.data)
                self.assertEqual(before.origins, after.origins)
        # CEVT belongs to the screen and applies to every preview layout.
        screen = compiled.string_ids["CFW_AlbumArtists_Screen"]
        layout = compiled.string_ids["CFW_AlbumArtists_Layout"]
        native_layout = resources.stock("SLst", "MediaLists_Artists_Screen")
        self.assertEqual(len(blocks(native_layout)), 1)
        self.assertEqual(word(blocks(resources.added["SLst", screen])[0][1], 0), layout)
        for kind, new_id, original in (
            ("SCST", screen, "MediaLists_Artists_Screen"),
            ("CEVT", screen, "MediaLists_Artists_Screen"),
            ("SEVT", layout, "MediaLists_Artists_Screen_Default"),
        ):
            self.assertEqual(
                resources.added[kind, new_id].origins,
                resources.stock(kind, original).origins,
            )
        header = emit_header(document, compiled.string_ids)
        self.assertIn("#define CFW_AlbumArtists_Screen ", header)

    def test_song_info_rows_are_dynamic_text_without_chosen_actions(self):
        root = Path(__file__).resolve().parents[2]
        metadata = json.loads((root / "firmware/ui.json").read_text())
        shim = root / "payload/native"
        bindings = json.loads((shim / "ui.json").read_text())["bindings"]
        resources = Resources(metadata["resources"], bindings)
        document = parser.read(root / "payload/song_info.ui")
        compiled = compile_document(resources, document)
        screen = compiled.string_ids["CFW_SongInfo_Screen"]
        self.assertEqual(word(resources.added["CEVT", screen], 0), 0)
        rows = [
            row
            for (kind, _), data in resources.added.items()
            if kind == "ITEM"
            for _, row in blocks(data)
        ]
        self.assertEqual(len(rows), 16)
        self.assertTrue(all(word(row, 0x60) == 2 for row in rows))
        for item in document.root.items:
            string_id = compiled.string_ids[item.name]
            self.assertEqual(
                bytes(resources.added["Str ", string_id].data),
                (item.title + ": Unknown\0").encode(),
            )
        for item_event in document.events:
            layouts = blocks(resources.stock("SLst", item_event.screen))
            self.assertTrue(layouts)
            for _, layout in layouts:
                self.assertIn(
                    b"contextualMenu.CFW_SongInfo",
                    resources.added["SEVT", word(layout, 0)].data,
                )
        header = emit_header(document, compiled.string_ids)
        self.assertIn("#define CFW_SongInfo_Screen ", header)
        self.assertIn("#define CFW_SongInfo_Layout ", header)

    def test_named_screen_uses_selected_binding_and_rejects_missing_names(self):
        document = parser.parse(
            '<ui><screen-event screen="Songs" event="select" handler="Select"/></ui>'
        )
        resources = Resources([], {"Songs": 10})
        resources.original = {
            ("SLst", 10): pack_blocks([(0, struct.pack("<I", 20))]),
            ("SEVT", 20): struct.pack("<I", 0),
        }
        resources.bind_screen_event(document.events[0])
        self.assertEqual(resources.added["SEVT", 20].word(0), 1)
        resources.bindings.clear()
        with self.assertRaises(KeyError):
            resources.bind_screen_event(document.events[0])

    def test_screen_events_extend_each_layout_without_replacing_stock_events(self):
        document = parser.parse(
            '<ui><screen-event screen="10" event="contextualMenu.CFW_PlayNext" '
            'handler="CFW_PlayNext"/></ui>'
        )
        stock = struct.pack("<I", 1) + event("button.menu.up", "navigator.PopTopScreen")
        resources = Resources([])
        resources.original = {
            ("SLst", 10): pack_blocks(
                [(0, struct.pack("<I", 20)), (0, struct.pack("<I", 21))]
            ),
            ("SEVT", 20): stock,
            ("SEVT", 21): stock,
        }
        resources.bind_screen_event(document.events[0])
        resources.bind_screen_event(ScreenEvent(10, "test.other", "OtherHandler"))
        for layout in (20, 21):
            data = resources.added["SEVT", layout]
            self.assertEqual(data.word(0), 3)
            self.assertEqual(data.data[4 : len(stock)], stock[4:])
            self.assertIn(b"contextualMenu.CFW_PlayNext1", data.data)
            self.assertIn(b"CFW_PlayNext\0\0\0\0", data.data)
            self.assertIn(b"test.other1", data.data)
            self.assertEqual(resources.original["SEVT", layout], stock)

    def test_storage_slots_survive_menu_reordering(self):
        first = selector("FIRST", 0)
        second = selector("SECOND", 1, 1)
        document = parser.parse(menu([second, first]))
        self.assertEqual([f.name for f in document.fields], ["FIRST", "SECOND"])
        self.assertEqual([f.name for f in document.root.items], ["SECOND", "FIRST"])
        header = emit_header(document)
        self.assertIn("FIRST = 0", header)
        self.assertIn("SECOND = 1", header)
        self.assertIn("TEST_FIELDS = 2", header)

    def test_invalid_declarations_fail_before_resource_generation(self):
        cases = [
            [selector("FIELD", 0, values="missing")],
            [selector("FIELD", 0, 2)],
            [selector("FIRST", 0), selector("SECOND", 0)],
            [selector("FIELD", 1)],
            [selector("FIELD", 0), selector("FIELD", 1)],
            [selector("FIELD", -1)],
            [selector("FIELD", 100)],
            [selector("bad-name", 0)],
        ]
        for rows in cases:
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                parser.parse(menu(rows))

    def test_malformed_or_unknown_xml_fails(self):
        for data in (
            "bad",
            "<ui><menu></ui>",
            menu([]),
            "<ui/>",
            "<other/>",
            '<ui><string id="NAME" text="Text" typo="1"/></ui>',
            '<ui><string id="NAME"/></ui>',
            "<ui><unknown/></ui>",
            '<ui><string id="NAME" text="Text">unexpected</string></ui>',
            '<ui><string id="NAME" text="Text"/>unexpected</ui>',
            '<ui><text id="PAGE" title="Page" file="page.txt" body="bad-name"/></ui>',
            '<ui><text id="PAGE" title="Page" file="page.txt" body="PAGE"/></ui>',
            '<ui><menu id="MENU" title="Menu"><string id="NAME" text="Text"/></menu></ui>',
            '<ui><text id="PAGE" title="Page" file="page.txt"/>'
            '<settings-entry menu="OTHER" after="1"/></ui>',
        ):
            with self.subTest(data=data), self.assertRaises(ValueError):
                parser.parse(data)

    def test_invalid_ranges_fail(self):
        for numbers in (
            (0, 10, 0, 10, 0),
            (0, 10, -1, 10, 0),
            (0, 10, 1, 3, 0),
            (0, 100, 1, 10, 0),
        ):
            first, last, step, scale, _ = numbers
            data = (
                f'<ui><range id="values" first="{first}" last="{last}" '
                f'step="{step}" scale="{scale}"/>'
                '<string id="NAME" text="Text"/></ui>'
            )
            with self.subTest(numbers=numbers), self.assertRaises(ValueError):
                parser.parse(data)

    def test_ranges_keep_scaled_labels_and_default_indices(self):
        document = parser.parse("""<ui>
          <range id="gain_values" first="-5" last="5" step="5"
                 scale="10" suffix=" dB" signed="true"/>
          <range id="precut" first="0" last="-10" step="-5" scale="10"/>
          <menu id="EQ" title="EQ">
            <menu id="BAND" title="Band">
              <selector id="GAIN" title="Gain" values="gain_values" slot="0" default="0"/>
            </menu>
          </menu>
        </ui>""")
        self.assertEqual(
            document.values["gain_values"].labels, ["-0.5 dB", "0.0 dB", "+0.5 dB"]
        )
        self.assertEqual(document.values["precut"].numbers, [0, -5, -10])
        self.assertEqual(document.fields[0].default_index, 1)
        self.assertIs(document.root.items[0].items[0], document.fields[0])

    def test_xml_text_and_hex_resource_ids(self):
        document = parser.parse("""<ui>
          <string id="LABEL" text="Music &amp; café &quot;mix&quot;"/>
          <screen-event screen="0x0DAD07B5" event="select" handler="Select"/>
        </ui>""")
        self.assertEqual(document.strings["LABEL"], 'Music & café "mix"')
        self.assertEqual(document.events[0].screen, 0x0DAD07B5)

    def test_native_bindings_follow_rows_but_actions_keep_storage_slots(self):
        document = parser.parse(
            menu(
                [
                    '<action id="TEST_Save" title="Save" values="choices"/>',
                    selector("SECOND", 1, 1),
                    selector("FIRST", 0),
                ]
            )
        )
        resources = Resources(
            [],
            {
                "SettingsMenu_ListItem_Legal": LEGAL_ITEM,
                "SettingsMenu_Items": 0x41,
                "SettingsMenus_Main_Screen": MAIN_SCREEN,
                "Notes_List_Screen_Alt": 0x0DAD09C3,
                "Notes_List_Screen_Alt_Default": 0x0DAD09C4,
            },
        )
        row = bytearray(0x98)
        struct.pack_into("<I", row, 0x30, LEGAL_ITEM)
        resources.original = {
            ("ITEM", 0x41): pack_blocks([(0, row)]),
            ("SCST", MAIN_SCREEN): b"screen",
            ("SLst", 0x0DAD09C3): pack_blocks([(0, bytes(4))]),
            ("SLyt", 0x0DAD09C4): pack_blocks([(0, struct.pack("<I", 10))]),
            ("SSin", 10): pack_blocks([]),
            ("SEVT", 0x0DAD09C4): b"events",
        }
        resources.added, resources.names, resources.next_id = {}, {}, 0x0CF00000
        builder = DocumentCompiler(resources, document)
        builder.menu(document.root)
        self.assertEqual(builder.fields[0].parent_index, 2)
        self.assertEqual(builder.fields[1].parent_index, 1)
        self.assertEqual(builder.actions["TEST_Save"].index, 0)
        events = b"".join(
            bytes(data.data) if hasattr(data, "data") else data
            for (kind, _), data in resources.added.items()
            if kind == "CEVT"
        )
        self.assertIn(b"TEST_Set_00_00", events)
        self.assertIn(b"TEST_Set_01_01", events)


if __name__ == "__main__":
    unittest.main()
