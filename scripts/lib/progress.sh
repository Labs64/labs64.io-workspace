#!/usr/bin/env bash
# Colorized, per-step progress reporting for long-running workspace scripts.
#
# Usage:
#   source "$(dirname "${BASH_SOURCE[0]}")/lib/progress.sh"
#   run_step "Build auditflow" -- mvn -B -T 1C clean install -Dmaven.test.skip=true
#
# VERBOSE=1 (default): stream the wrapped command's output live, framed by a
#   themed start/end banner (clear success/failure + elapsed time per step).
# VERBOSE=0: suppress the command's output behind an animated banner instead,
#   only dumping it (last 60 lines) if the step fails.

VERBOSE="${VERBOSE:-0}"

if [[ -t 1 ]]; then
    C_RESET=$'\033[0m'; C_GREEN=$'\033[32m'; C_RED=$'\033[31m'; C_DIM=$'\033[2m'; C_BOLD=$'\033[1m'
else
    C_RESET=""; C_GREEN=""; C_RED=""; C_DIM=""; C_BOLD=""
fi

case $((RANDOM % 3)) in
    0) _PROGRESS_FRAMES=("🌑" "🌒" "🌓" "🌔" "🌝" "🌕" "🌖" "🌗" "🌘" "🌚") ;;
    1) _PROGRESS_FRAMES=("🕛" "🕧" "🕐" "🕜" "🕑" "🕝" "🕒" "🕞" "🕓" "🕟" "🕔" "🕠" "🕕" "🕡" "🕖" "🕢" "🕗" "🕣" "🕘" "🕤" "🕙" "🕥" "🕚" "🕦") ;;
    2) _PROGRESS_FRAMES=("⚪" "⚫" "🔵" "🔴" "🟢" "🟡" "🟣" "🟤") ;;
esac

# run_step "label" -- cmd arg1 arg2 ...
run_step() {
    local label="$1"; shift
    [[ "${1:-}" == "--" ]] && shift

    local start elapsed status
    start=$(date +%s)

    if [[ "$VERBOSE" == "1" ]]; then
        printf "%s%s %s%s\n" "$C_BOLD" "${_PROGRESS_FRAMES[RANDOM % ${#_PROGRESS_FRAMES[@]}]}" "$label" "$C_RESET"
        if ( "$@" ); then status=0; else status=$?; fi
    else
        local log
        log="$(mktemp)"
        "$@" >"$log" 2>&1 &
        local pid=$!
        local i=0
        if [[ -t 1 ]]; then
            while kill -0 "$pid" 2>/dev/null; do
                elapsed=$(( $(date +%s) - start ))
                printf "\r%s %s  %s(%ds)%s   " \
                    "${_PROGRESS_FRAMES[i % ${#_PROGRESS_FRAMES[@]}]}" "$label" "$C_DIM" "$elapsed" "$C_RESET"
                i=$((i + 1))
                sleep 0.3
            done
            printf "\r\033[K"
        fi
        if wait "$pid"; then status=0; else status=$?; fi
        if [[ $status -ne 0 ]]; then
            echo "--- $label output (last 60 lines) ---"
            tail -n 60 "$log"
        fi
        rm -f "$log"
    fi

    elapsed=$(( $(date +%s) - start ))
    if [[ $status -eq 0 ]]; then
        printf "%s✅ %s%s %s(%ds)%s\n" "$C_GREEN$C_BOLD" "$label" "$C_RESET" "$C_DIM" "$elapsed" "$C_RESET"
    else
        printf "%s❌ %s failed%s %s(%ds)%s\n" "$C_RED$C_BOLD" "$label" "$C_RESET" "$C_DIM" "$elapsed" "$C_RESET"
    fi
    return $status
}
