#include <assert.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include "../../runtime/nvn/tegra.h"

static void check(uint32_t width, uint32_t height, uint32_t x, uint32_t y, uint32_t rw, uint32_t rh) {
    const uint32_t bpp = 4;
    FormatInfo fmt = {4, 1, 1, FMT_COLOR, "test"};
    TexLayout layout = {width, height, 1, 1, 1, &fmt, 0, 0};
    tegra_layout_init(&layout);
    LevelLayout level = tegra_level(&layout, 0);
    size_t linear_size = (size_t)width * height * bpp;
    size_t rect_size = (size_t)rw * rh * bpp;
    uint8_t *linear = malloc(linear_size), *result = malloc(linear_size), *rect = malloc(rect_size);
    uint8_t *storage = calloc(1, tegra_total_size(&layout));
    assert(linear && result && rect && storage);
    for (size_t i = 0; i < linear_size; i++) linear[i] = (uint8_t)(i * 17 + 11);
    for (size_t i = 0; i < rect_size; i++) rect[i] = (uint8_t)(i * 37 + 3);
    tegra_swizzle(linear, storage, width, height, 1, bpp, level.block_height_log2, 0);
    tegra_swizzle_rect(rect, storage, width, height, x, y, rw, rh, bpp, level.block_height_log2);
    tegra_deswizzle(storage, result, width, height, 1, bpp, level.block_height_log2, 0);
    for (uint32_t row = 0; row < rh; row++)
        memcpy(linear + ((size_t)(y + row) * width + x) * bpp, rect + (size_t)row * rw * bpp, (size_t)rw * bpp);
    assert(memcmp(linear, result, linear_size) == 0);
    free(storage); free(rect); free(result); free(linear);
}

int main(void) {
    check(512, 256, 0, 15, 512, 15);  // the online mod's font-atlas strips
    check(37, 29, 3, 7, 23, 15);      // unaligned rectangle crossing GOB boundaries
    check(512, 256, 0, 255, 512, 1);  // the final short strip
    return 0;
}
