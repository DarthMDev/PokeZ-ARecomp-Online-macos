#include <assert.h>
#include <math.h>
#include <stdint.h>
#include <string.h>
#include "../runtime/settings.h"
#ifdef _WIN32
#include <windows.h>
#endif

Settings g_settings;
void za_camera_scale_offset(float v[3], float target_height, int percent);
void rt_za_camera_distance(uint64_t object, uint64_t caller);

static void check(int percent, float expected_x, float expected_y, float expected_z) {
    float v[3] = {4.0f, 3.0f, -2.0f};
    za_camera_scale_offset(v, 1.0f, percent);
    assert(fabsf(v[0] - expected_x) < 0.0001f);
    assert(fabsf(v[1] - expected_y) < 0.0001f);
    assert(fabsf(v[2] - expected_z) < 0.0001f);
}

int main(void) {
    check(50, 2.0f, 2.0f, -1.0f);
    check(100, 4.0f, 3.0f, -2.0f);
    check(150, 6.0f, 4.0f, -3.0f);
    check(200, 8.0f, 5.0f, -4.0f);
    check(1, 2.0f, 2.0f, -1.0f);
    check(999, 8.0f, 5.0f, -4.0f);
    g_settings.camera_distance = 150;
    rt_za_camera_distance(0, 0); // unrelated caller must never dereference a camera pointer
#ifdef _WIN32
    // Exercise the checked guest pointer and caller with an isolated synthetic camera object.
    uint8_t *object = VirtualAlloc((void *)(uintptr_t)0x7400000000ull, 4096, MEM_RESERVE | MEM_COMMIT, PAGE_READWRITE);
    assert(object != NULL);
    uint64_t vt = 0x7003c106a0ull;
    float original[3] = {4.0f, 3.0f, -2.0f}, height = 1.0f, actual[3];
    memcpy(object, &vt, sizeof vt);
    memcpy(object + 0x2c0, original, sizeof original);
    memcpy(object + 0x2e4, &height, sizeof height);
    rt_za_camera_distance((uint64_t)(uintptr_t)object, 0x7000099db8ull);
    assert(!memcmp(object + 0x2c0, original, sizeof original));
    rt_za_camera_distance((uint64_t)(uintptr_t)object, 0x7000371bf4ull);
    memcpy(actual, object + 0x2c0, sizeof actual);
    assert(actual[0] == 6.0f && actual[1] == 4.0f && actual[2] == -3.0f);
    g_settings.camera_distance = 100;
    memcpy(object + 0x2c0, original, sizeof original);
    rt_za_camera_distance((uint64_t)(uintptr_t)object, 0x7000371bf4ull);
    assert(!memcmp(object + 0x2c0, original, sizeof original));
    VirtualFree(object, 0, MEM_RELEASE);
#endif
    return 0;
}
