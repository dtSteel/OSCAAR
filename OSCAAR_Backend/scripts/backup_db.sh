#!/bin/bash
# OSCAAR Database Backup Script
# Schedule with cron: 0 2 * * * /home/oscaar/oscaar/scripts/backup_db.sh

DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR=/data/backups/db
APP_ENV=${APP_ENV:-demo}

mkdir -p $BACKUP_DIR

if [ "$APP_ENV" = "production" ]; then
    echo "Backing up PostgreSQL..."
    pg_dump -U oscaar -h localhost oscaar \
        | gzip > $BACKUP_DIR/oscaar_$DATE.sql.gz
    echo "Backup complete: $BACKUP_DIR/oscaar_$DATE.sql.gz"
else
    echo "Backing up SQLite..."
    cp /home/oscaar/oscaar/oscaar.db $BACKUP_DIR/oscaar_$DATE.db
    gzip $BACKUP_DIR/oscaar_$DATE.db
    echo "Backup complete: $BACKUP_DIR/oscaar_$DATE.db.gz"
fi

# Keep only the last 30 days of backups
find $BACKUP_DIR -name "oscaar_*" -mtime +30 -delete
echo "Old backups cleaned up."
