# Lumiose Online integration

This fork contains the Lumiose integration, the supplied launcher artwork and
the Lumiose mod module. It does not contain Pokémon game files, extracted game
assets, saves, or game code generated from a player's copy. Each player must
provide and extract their own Pokémon Legends: Z-A game, update and DLC.

The launcher checks releases from this fork. The artwork is embedded into the
launcher executable during its build.

## Windows integration from a source checkout

The Lumiose integration is currently an experimental Windows workflow; it is
not yet a self-contained public release installer. Build the launcher with the
Windows instructions, and use ZA Recomp's normal setup to make `extracted/`
and its game library from your own game files. The game must be version 2.0.2.
The integration scripts require Python with `unicorn`, `capstone` and `lz4`,
the built `build/lasrecomp.dll.a`, and ZA Recomp's Zig distribution.

From the repository root, with that Python environment active, run:

```
python tools/lumiose/setup.py --install "PATH_TO_RECOMP_INSTALL" --zig "PATH_TO_ZIG_DIRECTORY" --server "RELAY_HOST:PORT"
```

This uses only the local player's game files to prepare the matching mod and
game libraries in their installation. It prints the command to start Lumiose
afterward. The scripts write their work files into the installation, not this
repository. Do not commit that output.

When the mod downloads an update, close the game as directed and use the same
start command. The updater prepares the matching libraries and tests startup
before activating them. It blocks startup and reports an error if an update is
older or its compatibility signatures no longer match; a future mod version
may require integration changes. The launcher release check is separate from
the mod's own update mechanism.
