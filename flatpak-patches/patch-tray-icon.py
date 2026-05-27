#!/usr/bin/env python3
"""Patch src-tauri/src/lib.rs to remove tray-icon dependency.

The upstream source unconditionally imports tauri::tray::TrayIconBuilder
and constructs a tray icon.  In the GNOME Flatpak sandbox, libappindicator
is not available, so the tray-icon feature causes a runtime panic.

This script strips:
  - The `tray::TrayIconBuilder,` import line
  - The menu-item boilerplate and TrayIconBuilder::new() block
  - Replaces the block with `let _ = app;` (a no-op)

Uses line-based delimiters for reliability across upstream changes.
"""

import sys


def patch_lib_rs(path: str) -> None:
    with open(path) as f:
        lines = f.readlines()

    out: list[str] = []

    # Lines to skip (exact match)
    tray_import = "    tray::TrayIconBuilder,\n"

    # Start and end markers for the menu + tray setup block
    block_start = '                let open_menu_item = MenuItem::with_id(app, "open", "Open", true, None::<&str>)\n'
    block_end_contains = '.expect("error while setting up tray menu")'

    skip_until_block_end = False

    for line in lines:
        if line == tray_import:
            continue  # skip the tray import

        if line == block_start:
            skip_until_block_end = True
            continue  # skip first line of block

        if skip_until_block_end:
            if block_end_contains in line:
                # Last line of the skipped block; the next meaningful
                # line is `                });` which we replace with `let _ = app;`
                skip_until_block_end = False
            continue

        out.append(line)

    # Replace the first `                });\n` after the patched block
    # with a no-op.  The tray setup block ends with:  });  });  (nested
    # closures), and we need to preserve the outer `});`.
    for i, line in enumerate(out):
        if line == "                });\n":
            # This is the closing of the menu/tray setup closure.
            # Insert `let _ = app;` before it and move on.
            out[i] = "                let _ = app;\n                });\n"
            break

    with open(path, "w") as f:
        f.writelines(out)

    print("Patched lib.rs: removed tray-icon code")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <lib.rs>", file=sys.stderr)
        sys.exit(1)
    patch_lib_rs(sys.argv[1])
