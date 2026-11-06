// Test cursor capture and touch mapping without a physical controller.
#include <SDL3/SDL.h>
static void input_reset(void);
static void input_load_user_mappings(void);
static bool input_user_blocked(const SDL_Event *e);
static int input_pad_family(void);
static void input_handle_event(const SDL_Event *e);
static void input_frame(uint64_t frame);
static uint64_t input_buttons_now(void);
#include "../../runtime/hle.h"
#undef HLE_FUNC
#define HLE_FUNC(sym, fn) static void fn(Cpu *c)
#undef RT_ON_RESET
#define RT_ON_RESET(fn) static void fn(void)
#include "../../runtime/hle/input.c"
#include <assert.h>

Settings g_settings = {.mouse_camera = MOUSE_CAM_CAPTURED};
int16_t g_bind_mouse[MOUSEB_COUNT] = {-1, -1, -1, -1, -1};
bool g_replay_handed;
int bind_label_family(void) { return 0; }
static bool focused = true, relative, cursor_visible;
bool menu_input_captured(void) { return false; }
bool menu_cursor_needed(void) { return false; }
SDL_WindowFlags SDL_GetWindowFlags(SDL_Window *window) { (void)window; return focused ? SDL_WINDOW_INPUT_FOCUS : 0; }
bool SDL_SetWindowRelativeMouseMode(SDL_Window *window, bool enabled) { (void)window; relative = enabled; return true; }
bool SDL_ShowCursor(void) { cursor_visible = true; return true; }
bool SDL_GetWindowSize(SDL_Window *window, int *w, int *h) { (void)window; *w = 1280; *h = 720; return true; }

int main(void) {
    SDL_Window *window = (SDL_Window *)1;
    input_mouse_update(window);
    assert(relative && mouse_held && !mouse_touch_enabled());
    keys_down[SDL_SCANCODE_LALT] = 1;
    input_mouse_update(window);
    assert(!relative && !mouse_held && mouse_touch_enabled() && cursor_visible);
    uint64_t p = touch_position(640, 360);
    assert((p & TOUCH_VALID) && (uint32_t)p == 640 && (uint32_t)(p >> 32) == (0x80000000u | 360));
    assert(!touch_position(-1, 0) && !touch_position(1280, 720));
    keys_down[SDL_SCANCODE_LALT] = 0;
    input_mouse_update(window);
    assert(relative && mouse_held && !mouse_touch_enabled());
    keys_down[SDL_SCANCODE_LALT] = 1;
    focused = false; input_mouse_update(window);
    assert(!relative && !keys_down[SDL_SCANCODE_LALT]);
    puts("mouse capture, Alt touch mode, coordinates and focus passed");
    return 0;
}
