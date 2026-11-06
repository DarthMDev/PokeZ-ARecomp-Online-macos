// Lumiose saves its interface settings on the emulated SD card.
#pragma once
#include <stdio.h>

typedef struct { float ui, text; } LumioseChatScale;

static inline LumioseChatScale lumiose_chat_scale_read(const char *save_dir) {
    LumioseChatScale result = {1.0f, 1.0f};
    char path[1200], line[256];
    if (!save_dir || snprintf(path, sizeof path, "%s/sdcard/lumiose_settings.txt", save_dir) >= (int)sizeof path)
        return result;
    FILE *file = fopen(path, "r");
    if (!file) return result;
    while (fgets(line, sizeof line, file)) {
        int value;
        if (sscanf(line, "ui_size = %d", &value) == 1 && value >= 50 && value <= 300) result.ui = value / 100.0f;
        else if (sscanf(line, "text_size = %d", &value) == 1 && value >= 50 && value <= 300) result.text = value / 100.0f;
    }
    fclose(file);
    return result;
}
