#!/usr/bin/env python3
"""Patch src-tauri/src/lib.rs to remove tray-icon dependency.

The upstream source unconditionally imports tauri::tray::TrayIconBuilder
and constructs a tray icon.  In the GNOME Flatpak sandbox, libappindicator
is not available, so the tray-icon feature causes a runtime panic.

Removes the tray import line and the menu+run_on_tray setup block,
replacing with a no-op `let _ = app;`.
"""

import sys


def patch_lib_rs(path: str) -> None:
    with open(path) as f:
        lines = f.readlines()

    out: list[str] = []

    import_line = "    tray::TrayIconBuilder,\n"
    block_start = '                let open_menu_item = MenuItem::with_id(app, "open", "Open", true, None::<&str>)\n'
    block_end_marker = '.expect("error while setting up tray menu")'

    state = "passthrough"  # passthrough | skipping_block | drop_one

    for line in lines:
        if line == import_line:
            continue

        if state == "passthrough":
            if line == block_start:
                state = "skipping_block"
                continue
            out.append(line)

        elif state == "skipping_block":
            if block_end_marker in line:
                state = "drop_one"
            # skip this line either way
            continue

        elif state == "drop_one":
            # This is the `                });` closing run_on_tray(...)
            # We drop it and insert the no-op.
            out.append("                let _ = app;\n")
            state = "passthrough"
            continue

    with open(path, "w") as f:
        f.writelines(out)

    print("Patched lib.rs: removed tray-icon code")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <lib.rs>", file=sys.stderr)
        sys.exit(1)
    patch_lib_rs(sys.argv[1])
