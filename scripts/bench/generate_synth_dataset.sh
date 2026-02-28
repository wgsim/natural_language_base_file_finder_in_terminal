#!/usr/bin/env bash
set -euo pipefail

OUTPUT_DIR="${1:-/tmp/askfind_bench_synth}"
PY_FILES="${PY_FILES:-1500}"
TODO_FILES="${TODO_FILES:-600}"
BINARY_FILES="${BINARY_FILES:-120}"
BINARY_BYTES="${BINARY_BYTES:-65536}"

if ! [[ "$PY_FILES" =~ ^[0-9]+$ ]] || ! [[ "$TODO_FILES" =~ ^[0-9]+$ ]] || ! [[ "$BINARY_FILES" =~ ^[0-9]+$ ]] || ! [[ "$BINARY_BYTES" =~ ^[0-9]+$ ]]; then
  echo "Error: PY_FILES, TODO_FILES, BINARY_FILES, and BINARY_BYTES must be non-negative integers." >&2
  exit 2
fi

mkdir -p "$OUTPUT_DIR/src" "$OUTPUT_DIR/docs" "$OUTPUT_DIR/logs"

for i in $(seq 1 "$PY_FILES"); do
  cat > "$OUTPUT_DIR/src/file_${i}.py" <<EOF
def f_${i}(x):
    if x > 0:
        return x
    return 0
EOF
done

for i in $(seq 1 "$TODO_FILES"); do
  printf 'TODO item %s\n' "$i" > "$OUTPUT_DIR/docs/note_${i}.md"
done

for i in $(seq 1 "$BINARY_FILES"); do
  head -c "$BINARY_BYTES" /dev/urandom > "$OUTPUT_DIR/logs/blob_${i}.bin"
done

echo "Synthetic benchmark dataset generated:"
echo "- root: $OUTPUT_DIR"
echo "- python files: $PY_FILES"
echo "- todo markdown files: $TODO_FILES"
echo "- binary files: $BINARY_FILES ($BINARY_BYTES bytes each)"
