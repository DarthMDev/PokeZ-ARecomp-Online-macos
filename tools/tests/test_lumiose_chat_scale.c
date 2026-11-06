#include "../../runtime/ui/lumiose_chat_layout.h"
#include <assert.h>
#include <math.h>
#include <stdio.h>

int main(int argc, char **argv) {
    assert(argc == 2);
    LumioseChatScale s = lumiose_chat_scale_read(argv[1]);
    assert(fabsf(s.ui - 1.0f) < 0.001f && fabsf(s.text - 1.0f) < 0.001f);
    char path[1200]; snprintf(path, sizeof path, "%s/sdcard/lumiose_settings.txt", argv[1]);
    FILE *f = fopen(path, "w"); assert(f);
    fputs("# settings\nui_size=125\ntext_size=80\n", f); fclose(f);
    s = lumiose_chat_scale_read(argv[1]);
    assert(fabsf(s.ui - 1.25f) < 0.001f && fabsf(s.text - 0.8f) < 0.001f);
    f = fopen(path, "w"); assert(f);
    fputs("ui_size=0\ntext_size=99999\n", f); fclose(f);
    s = lumiose_chat_scale_read(argv[1]);
    assert(fabsf(s.ui - 1.0f) < 0.001f && fabsf(s.text - 1.0f) < 0.001f);
    remove(path);
    puts("Lumiose chat scale settings passed");
    return 0;
}
