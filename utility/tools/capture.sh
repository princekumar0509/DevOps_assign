#!/usr/bin/env bash
# capture.sh - source this to record real command transcripts.
#
#   source utility/tools/capture.sh
#   log_init utility/transcripts/session-13/01_emptydir.log
#   run 'kubectl apply -f emptydir-pod.yaml'
#
# Every command is written as "$ <command>" and then evaluated exactly as
# written; its real stdout+stderr is appended underneath. Nothing is edited
# afterwards - termshot.py renders the .log into the PNG screenshot.

# a real terminal type + LS_COLORS so colour output matches gnome-terminal
export TERM=xterm-256color
eval "$(dircolors -b)" 2>/dev/null
export PATH="$HOME/.local/bin:$HOME/.venvs/devops-tools/bin:$PATH"
export COLUMNS=140

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
export REPO_ROOT

_pretty_pwd() { pwd | sed "s|^$HOME|~|"; }

log_init() {           # log_init <logfile> [window-title]
    LOG="$(realpath -m "$1")"
    mkdir -p "$(dirname "$LOG")"
    : > "$LOG"
    [ -n "$2" ] && printf '#TITLE %s\n' "$2" >> "$LOG"
    printf '#CWD %s\n' "$(_pretty_pwd)" >> "$LOG"
}

log_cwd() { printf '#CWD %s\n' "$(_pretty_pwd)" >> "$LOG"; }

run() {                # run '<shell command>'
    local before="$PWD"
    printf '$ %s\n' "$1" >> "$LOG"
    eval "$1" >> "$LOG" 2>&1
    local rc=$?
    printf '\n' >> "$LOG"
    [ "$PWD" != "$before" ] && log_cwd
    return $rc
}

run_ok() { run "$1" || true; }   # for commands whose non-zero exit is expected

# render the transcript just recorded into utility/screenshots/<same subdir>/
shot() {
    local rel="${LOG#"$REPO_ROOT"/utility/transcripts/}"
    local out="$REPO_ROOT/utility/screenshots/$(dirname "$rel")"
    /usr/bin/python3 "$REPO_ROOT/utility/tools/termshot.py" "$LOG" "$out"
}
