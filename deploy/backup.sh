#!/usr/bin/env bash
# Резервная копия базы (без остановки бота). Хранятся 14 последних копий, доступ — только root.
set -euo pipefail
DB=/opt/hashfan/game.db
DIR=/var/backups/hashfan
umask 077
mkdir -p "$DIR"
OUT="$DIR/game-$(date +%Y%m%d-%H%M).db"
python3 - "$DB" "$OUT" <<'PY'
import sqlite3, sys
src, dst = sqlite3.connect(sys.argv[1]), sqlite3.connect(sys.argv[2])
with dst:
    src.backup(dst)   # согласованная копия даже во время работы бота
dst.close(); src.close()
PY
gzip -f "$OUT"
ls -1t "$DIR"/game-*.db.gz | tail -n +15 | xargs -r rm -f
echo "Backup: $OUT.gz"
