#include "../../runtime/hle/swkbd.c"
#include <assert.h>

Module g_modules[4];
int g_nmodules;
static int seen_limit;
static bool seen_chat;

int menu_keyboard_run(const char *initial, int max_len, char *out, int cap, bool chat) {
    (void)initial;
    seen_limit = max_len;
    seen_chat = chat;
    snprintf(out, cap, "A message longer than eight characters");
    return 1;
}

int main(void) {
    uint8_t arg[0x500] = {0};
    uint16_t result[256] = {0};
    uint64_t out[2] = {(uintptr_t)result, sizeof result};
    Cpu c = {0};
    g_nmodules = 3;
    g_modules[2].base = 0x7006200000ull;
    g_modules[2].text_size = 0x1469a0;
    c.x[0] = (uintptr_t)out; c.x[1] = (uintptr_t)arg; c.x[30] = g_modules[2].base + 0x100;
    swkbd_show(&c);
    assert(seen_chat && seen_limit == 200 && result[8] != 0 && result[38] == 0);
    memset(result, 0, sizeof result);
    *(int32_t *)(arg + 0x3ac) = 12;
    c.x[0] = (uintptr_t)out; c.x[1] = (uintptr_t)arg; c.x[30] = 0x7000000100ull;
    swkbd_show(&c);
    assert(!seen_chat && seen_limit == 12);
    return 0;
}
