#!/usr/bin/env bash
set -euo pipefail

# Detect session type
SESSION="${XDG_SESSION_TYPE:-x11}"

# Optional: set a window/app name to focus before sending keys.
# Leave empty to send to whatever is focused.
APP_NAME="${APP_NAME:-}"   # e.g., APP_NAME="Chromium"

# Wait until a GUI session is ready
for i in {1..30}; do
  if [[ "$SESSION" == "x11" ]]; then
    export DISPLAY=${DISPLAY:-:0}
    export XAUTHORITY=${XAUTHORITY:-"/home/$USER/.Xauthority"}
    if xdotool getwindowfocus >/dev/null 2>&1; then break; fi
  else
    # Wayland: dbus must exist for many desktops; just give the session a moment
    if [[ -n "${XDG_RUNTIME_DIR:-}" ]]; then break; fi
  fi
  sleep 1
done

focus_app_x11() {
  [[ -z "$APP_NAME" ]] && return 0
  WID="$(xdotool search --onlyvisible --name "$APP_NAME" | head -n1 || true)"
  [[ -n "$WID" ]] && xdotool windowactivate --sync "$WID"
}

focus_app_wayland() {
  # Wayland generally blocks programmatic window focus. We just try sending keys.
  return 0
}

send_ctrl_tab_x11() { xdotool key ctrl+Tab; }
send_f5_x11()       { xdotool key F5;      }

send_ctrl_tab_wayland() { wtype -M ctrl -k TAB -m ctrl; }
send_f5_wayland()       { wtype -k F5; }

if [[ "$SESSION" == "wayland" ]]; then
  focus_app=focus_app_wayland
  press_ctrl_tab=send_ctrl_tab_wayland
  press_f5=send_f5_wayland
else
  focus_app=focus_app_x11
  press_ctrl_tab=send_ctrl_tab_x11
  press_f5=send_f5_x11
fi

# Main loop
while true; do
  "$focus_app"
  "$press_ctrl_tab"
  sleep 0.1
  "$press_f5"
  sleep 600
done
