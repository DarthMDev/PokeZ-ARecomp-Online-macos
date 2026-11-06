// Experimental entry point for a locally translated Lumiose module.
#include "gamelib.h"

extern const uint64_t lumiose_fn_addrs[], lumiose_fn_count;
extern const GuestFn lumiose_fn_ptrs[];

typedef struct { const uint64_t *addrs; const GuestFn *fns; uint64_t count; } ExtraTable;

GAMELIB_EXPORT const ExtraTable *lumiose_test_table(void) {
    static ExtraTable table;
    table.addrs = lumiose_fn_addrs;
    table.fns = lumiose_fn_ptrs;
    table.count = lumiose_fn_count;
    return &table;
}
