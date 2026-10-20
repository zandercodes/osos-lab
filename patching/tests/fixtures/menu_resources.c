/* SPDX-License-Identifier: GPL-3.0-only */
#include <assert.h>
#include <stddef.h>
#include <stdint.h>
#include <string.h>

#define CFW_OSOS_H
#define CFW_PATCH_H
#define PATCH_ARM
#define OSOS_MENU_ITEMS_REGISTER_TYPE register_items
struct osos_string { const char *data; };
static void register_items(uint32_t);
static void osos_resource_set(void *, uint32_t, uint32_t, const void *, uint32_t);
static const void *osos_resource_next(void *bank, uint32_t *id, uint32_t *size)
{
    (void)bank; (void)id; (void)size;
    return NULL;
}
static void osos_string_init(struct osos_string *s, const char *text) { s->data = text; }
static void osos_string_destroy(struct osos_string *s) { (void)s; }
static uint32_t name_id;
static int language = -1;
static unsigned language_queries, translation_probes;
static int osos_ui_language(void) { language_queries++; return language; }
static uint32_t *osos_resource_name_slot(const struct osos_string *s)
{
    (void)s;
    return &name_id;
}
#include "../../../payload/resources.h"
static const struct cfw_translation *translation_table(void);
#define cfw_translations translation_table()
#include "../../../payload/resources.c"
#undef cfw_translations

enum { ARTISTS = 1, ITUNES_U, NOW_PLAYING, ALBUM_ARTISTS };
struct row { uint32_t id, visible; };
static struct row main_stock[] = {{ARTISTS, 0}, {ITUNES_U, 1}, {NOW_PLAYING, 0}};
static struct row music_stock[] = {{ARTISTS, 1}, {ITUNES_U, 1}};
static const struct row main_copy[] = {
    {ARTISTS, 0}, {ALBUM_ARTISTS, 0}, {ITUNES_U, 1}, {NOW_PLAYING, 0}
};
static const struct row music_copy[] = {{ARTISTS, 1}, {ALBUM_ARTISTS, 1}, {ITUNES_U, 1}};
static struct row main_override[4], music_override[3];
static struct row *main_registry[5], *music_registry[5];
static unsigned installed, registered;
static int bank;
const struct cfw_resource cfw_resources[] = {
    {0x4954454d, 26, sizeof(main_copy), (const unsigned char *)main_copy},
    {0x4954454d, 27, sizeof(music_copy), (const unsigned char *)music_copy},
    {0x53747220, 200, 14, (const unsigned char *)"%1$s: %2$u%%"},
    {0x53747220, 201, 3, (const unsigned char *)"%s"},
    {0x53747220, 202, 3, (const unsigned char *)"%u"},
    {0x53747220, 203, 8, (const unsigned char *)"100%%!"},
};
const uint32_t cfw_resource_count = 6;
const struct cfw_resource_name cfw_resource_names[] = {{"AlbumArtists", ALBUM_ARTISTS}};
const uint32_t cfw_resource_name_count = 1;
const struct cfw_translation cfw_translations[] = {
    {100, 2, (const unsigned char *)"Francais"},
    {100, 4, (const unsigned char *)"Deutsch"},
    {101, 0, (const unsigned char *)"English"},
    {200, 4, (const unsigned char *)"%2$u%% - %1$s %1$s"},
};
const uint32_t cfw_translation_count = 4;
static const struct cfw_translation *translation_table(void)
{
    translation_probes++;
    return cfw_translations;
}
const struct cfw_format_spec cfw_formats[] = {
    {200, "su"}, {201, "s"}, {202, "u"}, {203, ""},
};
const uint32_t cfw_format_count = 4;

static void osos_resource_set(void *target, uint32_t type, uint32_t id,
                              const void *data, uint32_t size)
{
    if (type == 0x53747220) {
        assert(target == &bank && id >= 200 && id <= 203 && data && size);
        installed++;
        return;
    }
    assert(target == &bank && type == 0x4954454d && (id == 26 || id == 27));
    assert(size == (id == 26 ? sizeof(main_copy) : sizeof(music_copy)));
    memcpy(id == 26 ? main_override : music_override, data, size);
    installed++;
}

static void register_items(uint32_t type)
{
    assert(type == 0x4954454d && installed == cfw_resource_count);
    for (unsigned i = 0; i < 4; i++)
        main_registry[main_override[i].id] = &main_override[i];
    for (unsigned i = 0; i < 3; i++)
        music_registry[music_override[i].id] = &music_override[i];
    registered++;
}

int main(void)
{
    for (language = -1; language <= 21; language++) {
        for (uint32_t id = 0; id <= 201; id++) {
            const void *expected = NULL;
            int known_id = 0;
            for (uint32_t index = 0; index < cfw_translation_count; index++) {
                const struct cfw_translation *translation = &cfw_translations[index];
                if (translation->id == id) {
                    known_id = 1;
                    if (language >= 0 && translation->language == (uint32_t)language)
                        expected = translation->data;
                }
            }
            translation_probes = language_queries = 0;
            assert(cfw_translated_string(id) == expected);
            assert(translation_probes <= 3);
            assert(language_queries == (unsigned)known_id);
        }
        translation_probes = language_queries = 0;
        assert(!cfw_translated_string(UINT32_MAX));
        assert(translation_probes <= 3 && !language_queries);
    }
    language = -1;
    char formatted[64];
    assert(!strcmp(cfw_string(999), ""));
    assert(cfw_format(formatted, sizeof(formatted), 200, "value %u", (uint32_t)42));
    assert(!strcmp(formatted, "value %u: 42%"));
    language = 4;
    cfw_format(formatted, sizeof(formatted), 200, "Song", (uint32_t)3);
    assert(!strcmp(formatted, "3% - Song Song"));
    language = 20;
    cfw_format(formatted, sizeof(formatted), 200, "Song", (uint32_t)0);
    assert(!strcmp(formatted, "Song: 0%"));
    cfw_format(formatted, sizeof(formatted), 202, UINT32_MAX);
    assert(!strcmp(formatted, "4294967295"));
    cfw_format(formatted, sizeof(formatted), 203);
    assert(!strcmp(formatted, "100%!"));
    cfw_format(formatted, sizeof(formatted), 201, (const char *)NULL);
    assert(!*formatted);
    assert(!cfw_format(NULL, 0, 201, "ignored"));
    cfw_format(formatted, 1, 201, "x");
    assert(!*formatted);
    cfw_format(formatted, 3, 201, "A\xc3\xa4Z");
    assert(!strcmp(formatted, "A"));
    cfw_format(formatted, 4, 201, "A\xc3\xa4Z");
    assert(!strcmp(formatted, "A\xc3\xa4"));
    cfw_format(formatted, sizeof(formatted), 999);
    assert(!*formatted);
    language = -1;
    assert(!cfw_translated_string(100));
    language = 4;
    assert(!strcmp(cfw_translated_string(100), "Deutsch"));
    assert(!cfw_translated_string(999));
    language = 0;
    assert(!cfw_translated_string(100));
    assert(!strcmp(cfw_translated_string(101), "English"));
    language = 2;
    assert(!strcmp(cfw_translated_string(100), "Francais"));
    language = 20;
    assert(!cfw_translated_string(100));
    for (unsigned i = 0; i < 3; i++)
        main_registry[main_stock[i].id] = &main_stock[i];
    for (unsigned i = 0; i < 2; i++)
        music_registry[music_stock[i].id] = &music_stock[i];
    cfw_install_resources(&bank);
    assert(registered == 1 && name_id == ALBUM_ARTISTS);

    /* Settings and playback must update the same rows that the menus display. */
    main_registry[ARTISTS]->visible = 1;
    main_registry[ITUNES_U]->visible = 0;
    main_registry[NOW_PLAYING]->visible = 1;
    main_registry[ALBUM_ARTISTS]->visible = 1;
    music_registry[ITUNES_U]->visible = 0;
    music_registry[ALBUM_ARTISTS]->visible = 0;
    assert(main_override[0].visible == 1 && main_override[1].visible == 1);
    assert(main_override[2].visible == 0 && main_override[3].visible == 1);
    assert(music_override[1].visible == 0 && music_override[2].visible == 0);
    assert(main_stock[0].visible == 0 && main_stock[1].visible == 1);
    assert(main_stock[2].visible == 0 && music_stock[1].visible == 1);
    return 0;
}
