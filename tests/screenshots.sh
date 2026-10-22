#!/bin/sh
# Screenshots unter Linux: virtueller Bildschirm + Fenstermanager + Infobereich.
# Aufruf: tests/screenshots.sh <Zielordner> [--dark]
# Braucht: Xvfb, openbox, stalonetray, xdotool, xwininfo, ImageMagick (import).
OUT="${1:-screenshots}"; shift
export DISPLAY=:77
Xvfb :77 -screen 0 1440x900x24 >/dev/null 2>&1 & XVFB=$!
sleep 1
openbox >/dev/null 2>&1 & WM=$!
stalonetray --geometry 6x1-0-0 --icon-size 24 --background '#1f2329' >/dev/null 2>&1 & TRAY=$!
sleep 1
python3 "$(dirname "$0")/screenshots.py" "$OUT" "$@"
STATUS=$?
kill $TRAY $WM $XVFB 2>/dev/null
exit $STATUS
