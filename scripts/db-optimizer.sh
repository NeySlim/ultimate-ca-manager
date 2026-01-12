#!/bin/bash
# UCM Database Optimizer Wrapper

set -e

# Load environment
set -a
[ -f /etc/ucm/ucm.env ] && source /etc/ucm/ucm.env
set +a

# Change to backend directory
cd /opt/ucm/backend

# Use Flask to run optimization in app context
export FLASK_APP=wsgi:app

/opt/ucm/venv/bin/flask shell << 'PYTHON'
import logging
from services.db_management_service import DatabaseManagementService

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/var/log/ucm/db-optimizer.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

logger.info('='*60)
logger.info('UCM Database Optimizer - Starting')
logger.info('='*60)

service = DatabaseManagementService()
stats = service.get_database_stats()

if stats['size_mb'] < 10:
    logger.info('Skipping - DB too small (%.2f MB)' % stats['size_mb'])
    exit(0)

if stats['fragmentation_pct'] < 5:
    logger.info('Skipping - low fragmentation (%.2f%%)' % stats['fragmentation_pct'])
    exit(0)

logger.info('Size: %s, Fragmentation: %.2f%%' % (stats['size_formatted'], stats['fragmentation_pct']))

result = service.optimize_database()

if result['success']:
    v = result['vacuum']
    logger.info('✓ VACUUM: %.2f → %.2f MB (saved %s)' % (v['size_before_mb'], v['size_after_mb'], v['space_saved_formatted']))
    logger.info('✓ ANALYZE completed')
    logger.info('='*60)
else:
    logger.error('✗ Failed: %s' % result.get('error', 'Unknown'))
    exit(1)
PYTHON


