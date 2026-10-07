#!/usr/bin/env bash
# replay.sh - re-record a transcript from a command list and render its screenshot.
#
#   utility/tools/replay.sh <list.cmds> <transcripts/dir/name.log>
#
# The command list is the "$ " lines of an earlier transcript: an optional
# "#TITLE" line, one "#CWD <dir>" line (~/Devops-Assignments = repo root),
# then one shell command per line. "#SLEEP <s>" and "#WAIT <shell test>" lines
# pause (unrecorded) so a state like ImagePullBackOff has time to appear.
# Every command runs for real via capture.sh.
set -o pipefail
source "$(dirname "${BASH_SOURCE[0]}")/capture.sh"

cmds="$1"; out="$2"
title="$(sed -n 's/^#TITLE //p' "$cmds")"
cwd="$(sed -n 's/^#CWD //p' "$cmds" | head -1)"
cwd="${cwd/#\~\/Devops-Assignments/$REPO_ROOT}"

cd "$cwd" || exit 1
log_init "$out" ${title:+"$title"}
while IFS= read -r line; do
    case "$line" in
        '#SLEEP '*) sleep "${line#\#SLEEP }"; continue ;;            # pause, not recorded
        '#WAIT '*) timeout 180 sh -c "until ${line#\#WAIT }; do sleep 2; done" >/dev/null 2>&1; continue ;;
        '#'*|'') continue ;;
    esac
    run_ok "$line"
done < "$cmds"
shot >/dev/null
echo "recorded $(basename "$out")"
