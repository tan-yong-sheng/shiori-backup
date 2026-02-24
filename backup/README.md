# Shiori Backup System

A Python-based automated backup solution for Shiori bookmark manager, inspired by trilium-backup. Provides scheduled, encrypted, cloud-backed backups with support for both SQLite and PostgreSQL databases.

## Features

- **Automated Scheduling**: Cron-based backup scheduling
- **Database Support**: PostgreSQL (pg_dump), MySQL/MariaDB (mysqldump), SQLite (hot backup)
- **Compression**: tar.gz archive format
- **Encryption**: GPG AES256 encryption for backup archives
- **Cloud Storage**: Multi-destination upload via rclone (S3, R2, B2, GDrive, Dropbox, etc.)
- **Retention**: Automatic cleanup of old backups
- **Notifications**: Webhook and email notifications
- **Restore**: Cloud-first restore with integrity verification and safety backups

## Quick Start

1. **Configure rclone** for cloud storage:
   ```bash
   cp backup/rclone.conf.example backup/rclone.conf
   # Edit backup/rclone.conf with your credentials
   ```

2. **Set environment variables**:
   ```bash
   export BACKUP_ENCRYPTION_KEY=$(openssl rand -base64 32)
   export BACKUP_RCLONE_DESTINATIONS="r2:my-bucket/shiori-backups"
   ```

3. **Start the backup service**:
   ```bash
   docker-compose up -d backup
   ```

## Configuration

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `BACKUP_ENCRYPTION_KEY` | **Yes** | - | GPG passphrase for encryption |
| `BACKUP_RCLONE_DESTINATIONS` | **Yes** | - | Comma-separated destinations (e.g., `r2:bucket/shiori,s3:bucket/shiori`) |
| `SHIORI_DATABASE_URL` | *Cond* | - | PostgreSQL/MySQL connection URL |
| `SHIORI_DATA_DIR` | *Cond* | `/srv/shiori` | SQLite data directory |
| `BACKUP_SCHEDULE` | No | `0 2 * * *` | Cron schedule (default: daily 2 AM) |
| `BACKUP_RETENTION_DAYS` | No | `30` | Days to retain backups |
| `BACKUP_RUN_ON_START` | No | `false` | Run backup immediately on startup |
| `BACKUP_DELETE_LOCAL_AFTER_UPLOAD` | No | `false` | Delete local backup after cloud upload |
| `BACKUP_WEBHOOK_URL` | No | - | Webhook URL for notifications |
| `SMTP_HOST` | No | - | SMTP server for email notifications |
| `SMTP_PORT` | No | `587` | SMTP port |
| `SMTP_USER` | No | - | SMTP username |
| `SMTP_PASSWORD` | No | - | SMTP password |
| `SMTP_TO` | No | - | Email recipient |
| `LOG_LEVEL` | No | `INFO` | Logging level (DEBUG, INFO, WARNING, ERROR) |

### Docker Compose

The backup service is included in `docker-compose.yml`:

```yaml
backup:
  build: ./backup
  container_name: shiori-backup
  volumes:
    - "./dev-data:/srv/shiori:ro"          # Shiori data
    - "./backup/rclone.conf:/config/rclone/rclone.conf:ro"
    - "shiori-backups:/backups"             # Local backup storage
  environment:
    SHIORI_DATABASE_URL: postgres://shiori:shiori@postgres/shiori?sslmode=disable
    SHIORI_DATA_DIR: /srv/shiori
    BACKUP_SCHEDULE: "0 2 * * *"
    BACKUP_ENCRYPTION_KEY: ${BACKUP_ENCRYPTION_KEY}
    BACKUP_RCLONE_DESTINATIONS: ${BACKUP_RCLONE_DESTINATIONS}
  depends_on:
    - postgres
  restart: unless-stopped
```

## Backup Contents

The backup includes:
- **Database**: Full database dump (PostgreSQL/MySQL/SQLite)
- **Archives**: WARC files (`archive/`)
- **Thumbnails**: Thumbnail images (`thumb/`)
- **Ebooks**: Generated EPUB files (`ebook/`)

## Restore

### List Available Backups

```bash
# List cloud backups
docker exec shiori-backup python restore.py --list

# List local backups
docker exec shiori-backup python restore.py --list --source local
```

### Restore Latest Backup

```bash
# Restore from cloud (default)
docker exec -it shiori-backup python restore.py --restore-latest

# Restore from local
docker exec -it shiori-backup python restore.py --restore-latest --source local

# Force restore without confirmation
docker exec shiori-backup python restore.py --restore-latest --force
```

### Restore Specific Backup

```bash
# From cloud
docker exec -it shiori-backup python restore.py --restore r2:bucket/shiori-backup-20240115_020000.tar.gz.gpg

# From local
docker exec -it shiori-backup python restore.py --restore /backups/shiori-backup-20240115_020000.tar.gz.gpg
```

## Cloud Storage Configuration (rclone)

### Cloudflare R2 (Recommended)

```ini
[r2]
type = s3
provider = Cloudflare
access_key_id = YOUR_ACCESS_KEY
secret_access_key = YOUR_SECRET_KEY
endpoint = https://YOUR_ACCOUNT_ID.r2.cloudflarestorage.com
acl = private
```

### AWS S3

```ini
[s3]
type = s3
provider = AWS
access_key_id = YOUR_ACCESS_KEY
secret_access_key = YOUR_SECRET_KEY
region = us-east-1
acl = private
```

### Backblaze B2

```ini
[b2]
type = b2
account = YOUR_ACCOUNT_ID
key = YOUR_APPLICATION_KEY
```

## Manual Backup

Run a backup immediately:

```bash
# Using docker exec
docker exec shiori-backup python backup.py --now

# Or using Python directly in the container
docker exec shiori-backup python -c "from backup import create_backup; create_backup()"
```

## Security

- **Encryption**: All backups are encrypted with GPG AES256
- **Credentials**: Store sensitive values in environment variables, not in git
- **rclone.conf**: Contains cloud credentials - never commit this file

## Troubleshooting

### Check backup logs

```bash
docker logs shiori-backup
```

### Verify rclone configuration

```bash
docker exec shiori-backup rclone --config /config/rclone/rclone.conf listremotes
```

### Test cloud connection

```bash
docker exec shiori-backup rclone --config /config/rclone/rclone.conf ls r2:your-bucket
```

## File Structure

```
backup/
├── Dockerfile              # Multi-stage build with Python 3.12
├── requirements.txt        # Python dependencies
├── .env.example           # Environment variable template
├── rclone.conf            # rclone configuration (not in git)
├── rclone.conf.example    # rclone config template
├── README.md              # This file
└── src/
    ├── __init__.py
    ├── backup.py          # Main backup script with scheduler
    ├── restore.py         # Restore functionality
    ├── database.py        # Database handlers (SQLite, PostgreSQL, MySQL)
    ├── archive.py         # tar.gz creation/extraction
    ├── encryption.py      # GPG encryption/decryption
    ├── storage.py         # rclone cloud operations
    ├── retention.py       # Backup cleanup
    ├── notifications.py   # Webhook and email alerts
    └── utils.py           # Logging, config, helpers
```

## License

This backup system follows the same license as the Shiori project.
