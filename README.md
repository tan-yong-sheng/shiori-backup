# Shiori Docker Backup System

[![Docker Image](https://github.com/tan-yong-sheng/shiori-backup/actions/workflows/docker-build.yml/badge.svg)](https://github.com/tan-yong-sheng/shiori-backup/actions/workflows/docker-build.yml)

A Docker-based scheduled backup solution for [Shiori](https://github.com/go-shiori/shiori) bookmark manager with support for SQLite/PostgreSQL/MySQL, GPG encryption, and multi-cloud storage.

## Features

- **Multi-Database Support** - SQLite hot backups, PostgreSQL pg_dump, MySQL mysqldump
- **Complete Data Backup** - Database + archives (WARC) + thumbnails + ebooks
- **GPG AES256 Encryption** - Military-grade encryption for all backups
- **Multi-Cloud Storage** - Upload to multiple cloud providers via rclone (S3, R2, B2, GDrive, etc.)
- **Cloud-First Restore** - Restore directly from cloud to any machine
- **Automated Scheduling** - Cron-based backup scheduling
- **Retention Policy** - Automatic cleanup of old backups
- **Notifications** - Webhook and email alerts on backup success/failure

## Quick Start

### 1. Clone Repository

```bash
git clone https://github.com/tan-yong-sheng/shiori-backup.git
cd shiori-backup
```

### 2. Setup Files

```bash
mkdir -p dev-data shiori-docker-backups backup
cp .env.example .env
cp backup/rclone.conf.example backup/rclone.conf
```

### 3. Configure Environment

Edit `.env` (see [.env.example](.env.example) for all options):

```bash
# Required - Generate with: openssl rand -base64 32
BACKUP_ENCRYPTION_KEY=your-secure-passphrase-here

# Required - Cloud storage destination(s)
BACKUP_RCLONE_DESTINATIONS=r2:my-bucket/shiori-backups

# Optional - defaults shown
BACKUP_SCHEDULE=0 2 * * *      # Daily at 2 AM UTC
BACKUP_RETENTION_DAYS=7
BACKUP_RUN_ON_START=false
```

### 4. Configure Cloud Storage

Edit `backup/rclone.conf` (see [rclone.conf.example](backup/rclone.conf.example) for examples):

```ini
[r2]
type = s3
provider = Cloudflare
access_key_id = your-key
secret_access_key = your-secret
endpoint = https://your-account.r2.cloudflarestorage.com
acl = private
```

### 5. Choose Database Backend

#### Option A: SQLite (Simplest)

```bash
# Use docker-compose.sqlite.yml
docker-compose -f docker-compose.sqlite.yml up -d
```

#### Option B: PostgreSQL (Recommended for production)

```bash
# Use docker-compose.postgres.yml
docker-compose -f docker-compose.postgres.yml up -d
```

### 6. Verify

```bash
# Check backup logs
docker-compose logs -f backup

# List local backups
docker-compose exec backup ls -la /backups

# List cloud backups
docker-compose exec backup python restore.py --list
```

## Backup Operations

### Manual Backup

```bash
# Trigger immediate backup
docker-compose exec backup python backup.py --now
```

### List Backups

```bash
# List cloud backups
docker-compose exec backup python restore.py --list

# List local backups
docker-compose exec backup python restore.py --list --source local
```

## Restore from Backup

### Restore Latest Cloud Backup

```bash
# For SQLite
docker-compose -f docker-compose.sqlite.yml exec backup python restore.py --restore-latest --force

# For PostgreSQL
docker-compose -f docker-compose.postgres.yml exec backup python restore.py --restore-latest --force
```

### Restore Specific Backup

```bash
# From cloud
docker-compose exec backup python restore.py --restore r2:bucket/shiori-backup-20240224_020000.tar.gz.gpg --force

# From local
docker-compose exec backup python restore.py --restore /backups/shiori-backup-20240224_020000.tar.gz.gpg --force
```

## Disaster Recovery

On a new server:

```bash
git clone https://github.com/tan-yong-sheng/shiori-backup.git
cd shiori-backup

# Copy your .env and backup/rclone.conf from secure storage
cp /path/to/backup/.env .
cp /path/to/backup/rclone.conf backup/

# Start services
docker-compose -f docker-compose.sqlite.yml up -d
# OR for PostgreSQL:
# docker-compose -f docker-compose.postgres.yml up -d

# Restore from cloud
docker-compose exec backup python restore.py --restore-latest --force
```

## Documentation

| Document | Description |
|----------|-------------|
| [.env.example](.env.example) | All environment variables explained |
| [backup/rclone.conf.example](backup/rclone.conf.example) | Cloud storage configuration examples |
| [backup/README.md](backup/README.md) | Detailed backup system documentation |

## Supported Cloud Storage

Via rclone (configure in `backup/rclone.conf`):

- **Cloudflare R2** (recommended - S3-compatible, cost-effective)
- **AWS S3**
- **Backblaze B2**
- **Google Drive**
- **Dropbox**
- **Any rclone-supported provider**

## Available Images

```
ghcr.io/tan-yong-sheng/shiori-backup:latest
ghcr.io/tan-yong-sheng/shiori-backup:main
```

Supported architectures: `linux/amd64`, `linux/arm64`

## Configuration Reference

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `BACKUP_ENCRYPTION_KEY` | **Yes** | - | GPG passphrase for encryption |
| `BACKUP_RCLONE_DESTINATIONS` | **Yes** | - | Comma-separated cloud destinations |
| `SHIORI_DATABASE_URL` | *Cond* | - | PostgreSQL/MySQL connection URL |
| `SHIORI_DATA_DIR` | *Cond* | `/srv/shiori` | SQLite data directory |
| `BACKUP_SCHEDULE` | No | `0 2 * * *` | Cron schedule |
| `BACKUP_RETENTION_DAYS` | No | `7` | Days to retain backups |
| `BACKUP_RUN_ON_START` | No | `false` | Run backup on container start |
| `BACKUP_DELETE_LOCAL_AFTER_UPLOAD` | No | `false` | Delete local after cloud upload |
| `BACKUP_WEBHOOK_URL` | No | - | Webhook for notifications |

### Database Support

| Database | Configuration | Notes |
|----------|---------------|-------|
| **SQLite** | `SHIORI_DATA_DIR=/srv/shiori` | Default, file-based |
| **PostgreSQL** | `SHIORI_DATABASE_URL=postgres://...` | Production-ready |
| **MySQL/MariaDB** | `SHIORI_DATABASE_URL=mysql://...` | Alternative option |

## Testing

```bash
cd backup

# Run all tests
python -m pytest tests/ -v

# Run with coverage
python -m pytest tests/ --cov=src --cov-report=html
```

## Development

```bash
# Build local image
docker build -t shiori-backup:dev ./backup

# Run with local changes
docker-compose -f docker-compose.sqlite.yml up -d
```

## License

MIT License - See [LICENSE](LICENSE)

## Acknowledgments

- Inspired by [trilium-backup](https://github.com/tan-yong-sheng/trilium-backup)
- Built for [Shiori](https://github.com/go-shiori/shiori) bookmark manager
