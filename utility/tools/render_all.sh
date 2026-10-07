#!/usr/bin/env bash
# render_all.sh - regenerate every terminal screenshot from its transcript.
#
#   utility/tools/render_all.sh            # all sessions
#   utility/tools/render_all.sh session-14 # one session
#
# Terminal screenshots are derived data: transcripts/<dir>/<name>.log renders to
# screenshots/<dir>/<name>.png (or <name>_1.png, <name>_2.png ... when long).
# Browser captures are named web_*.png and are never touched here.
# Any other PNG without a matching transcript is reported as stale.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
T="$ROOT/utility/transcripts"
S="$ROOT/utility/screenshots"
only="${1:-}"

for dir in "$T"/*/; do
  name="$(basename "$dir")"
  [ -n "$only" ] && [ "$name" != "$only" ] && continue
  mkdir -p "$S/$name"
  find "$S/$name" -maxdepth 1 -name '*.png' ! -name 'web_*' -delete
  for log in "$dir"*.log; do
    /usr/bin/python3 "$ROOT/utility/tools/termshot.py" "$log" "$S/$name" >/dev/null
  done
  echo "rendered $(find "$S/$name" -name '*.png' ! -name 'web_*' | wc -l) screenshots for $name"
done

# anything left that is neither a browser capture nor backed by a transcript?
stale=0
while IFS= read -r png; do
  rel="${png#"$S"/}"; base="${rel%.png}"
  [ -f "$T/$base.log" ] && continue
  # multi-page renders are <name>_<page>.png
  [[ "$base" =~ ^(.*)_[0-9]+$ ]] && [ -f "$T/${BASH_REMATCH[1]}.log" ] && continue
  echo "STALE: $rel"; stale=1
done < <(find "$S" -name '*.png' ! -name 'web_*')
exit $stale
