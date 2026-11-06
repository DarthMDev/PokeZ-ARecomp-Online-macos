#include "../../runtime/lumiose_map_guard.h"
#include <assert.h>

int main(void) {
    const uint64_t game = 0x7000000000ull, mod = 0x7006200000ull, size = 0x150000;
    assert(lumiose_null_character_map(game + 0x649df8, game, 0, 0x700624c714ull, mod, size));
    assert(lumiose_null_character_map(game + 0x649d34, game, 0, 0x700624c714ull, mod, size));
    assert(!lumiose_null_character_map(game + 0x649df8, game, 1, 0x700624c714ull, mod, size));
    assert(!lumiose_null_character_map(game + 0x649dfc, game, 0, 0x700624c714ull, mod, size));
    assert(!lumiose_null_character_map(game + 0x649df8, game, 0, mod - 4, mod, size));
    assert(!lumiose_null_character_map(game + 0x649df8, game, 0, mod + size, mod, size));
    return 0;
}
