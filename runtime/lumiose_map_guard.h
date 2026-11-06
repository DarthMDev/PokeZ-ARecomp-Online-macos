// An optional Lumiose character-map lookup must not dereference a null map.
#pragma once
#include <stdbool.h>
#include <stdint.h>

static inline bool lumiose_null_character_map(uint64_t pc, uint64_t main_base, uint64_t object,
                                               uint64_t return_address, uint64_t mod_base, uint64_t mod_text_size) {
    return object == 0 && (pc == main_base + 0x649df8 || pc == main_base + 0x649d34) &&
           return_address >= mod_base && return_address - mod_base < mod_text_size;
}
