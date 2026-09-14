#!/bin/sh
# Run TLC on one spec config.
#   spec/run_tlc.sh Signals Signals.cfg
#   spec/run_tlc.sh Runtime broken/NoFencing.cfg
# Downloads tla2tools.jar into spec/.tools/ (gitignored) and refuses a jar whose
# sha256 differs from spec/tla2tools.sha256. Extra arguments go to TLC.
set -eu
cd "$(dirname "$0")"
JAVA=${JAVA:-/opt/homebrew/opt/openjdk/bin/java}   # the java on PATH is broken on this machine
JAR=.tools/tla2tools.jar
URL=https://github.com/tlaplus/tlaplus/releases/download/v1.8.0/tla2tools.jar
[ $# -ge 2 ] || { echo "usage: $0 <Module> <config.cfg> [tlc args]" >&2; exit 2; }
MOD=$1; CFG=$2; shift 2
if [ ! -f "$JAR" ]; then
  mkdir -p .tools
  curl -sSL -o "$JAR" "$URL"
fi
want=$(awk '{print $1}' tla2tools.sha256)
have=$(shasum -a 256 "$JAR" | awk '{print $1}')
if [ "$want" != "$have" ]; then
  echo "tla2tools.jar sha256 $have does not match pinned $want" >&2
  echo "(the v1.8.0 asset is a rolling build; re-pin deliberately if you updated it)" >&2
  exit 3
fi
META="states/$(echo "$CFG" | tr / _)"
rm -rf "$META"
exec "$JAVA" -XX:+UseParallelGC -Xmx${TLC_HEAP:-12g} -cp "$JAR" tlc2.TLC \
  -config "$CFG" -workers ${TLC_WORKERS:-auto} -metadir "$META" "$@" "$MOD.tla"
