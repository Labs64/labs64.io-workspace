#!/bin/bash
# Installed as `xclip` by post-create.sh, for tools such as gh that copy through xclip.
#
# The container has no X server to copy to. This script sends the text to the terminal as an
# OSC 52 escape sequence instead, and the terminal app (the VS Code integrated terminal on any
# host OS) puts it on the host's clipboard. A terminal without OSC 52 support ignores the
# sequence. Without a controlling terminal (Claude Code's `!` commands, scripts, CI) nothing is
# written, and the script still exits 0 so the caller does not report a clipboard error.
#
# OSC 52 cannot read the clipboard, so `xclip -o` fails.

set -uo pipefail

for arg in "$@"; do
    case "$arg" in
        -o | -out)
            echo "xclip: this container's xclip can copy but not paste" >&2
            exit 1
            ;;
    esac
done

data=$(base64 -w0)
{ printf '\033]52;c;%s\a' "$data" > /dev/tty; } 2> /dev/null || true
exit 0
