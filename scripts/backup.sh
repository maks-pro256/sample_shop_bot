#!/bin/sh
# Периодический бэкап PostgreSQL. Запускается в сервисе backup из docker-compose.yml.
# Подключение берётся из переменных PGHOST, PGUSER, PGPASSWORD, PGDATABASE.
set -o pipefail

INTERVAL_SECONDS="${BACKUP_INTERVAL_SECONDS:-86400}"
KEEP_DAYS="${BACKUP_KEEP_DAYS:-7}"
BACKUP_DIR=/backups

while true; do
    file="$BACKUP_DIR/shop_$(date +%Y-%m-%d_%H-%M).sql.gz"
    # --clean --if-exists: при восстановлении старые таблицы удаляются и создаются заново
    if pg_dump --clean --if-exists | gzip > "$file.tmp"; then
        mv "$file.tmp" "$file"
        echo "$(date '+%Y-%m-%d %H:%M:%S') | Бэкап создан: $file"
    else
        rm -f "$file.tmp"
        echo "$(date '+%Y-%m-%d %H:%M:%S') | ОШИБКА: бэкап не создан" >&2
    fi
    find "$BACKUP_DIR" -name 'shop_*.sql.gz' -mtime +"$KEEP_DAYS" -delete
    sleep "$INTERVAL_SECONDS"
done
