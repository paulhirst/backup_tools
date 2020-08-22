import argparse
import os.path
import signal
import datetime
import socket
import subprocess
import logging
import logging.handlers

def run(cmd, logger):
    logger.debug(f'running: {cmd}')
    ret = subprocess.run(cmd, capture_output=True)
    stdout = ret.stdout.decode('ASCII')
    stderr = ret.stderr.decode('ASCII')
    if ret.returncode == 0:
        logger.info(f'Appears to have completed sucessfully. {stdout}, {stderr}')
    else:
        logger.info(f'Failed with returncode {ret.returncode}: {stdout}, {stderr}')
    return ret.returncode

def getfile(name, path):
    # Get contents of file name in path, return as string.
    # Return None if file does not exist.
    filename = os.path.join(path, name)
    if os.path.exists(filename):
        with open(filename) as f:
            string = f.read()
        return string
    else:
        return None

def putfile(name, path, content):
    # Write content to file name in path
    filename = os.path.join(path, name)
    with open(filename, 'w') as f:
        f.write(content)

def get_label(argsrc):
    # Make a label (name) for this backup, using the args and datetime now
    dt = datetime.datetime.utcnow().isoformat(timespec='seconds')
    # Get src with leading and trailing slashes removed
    src = argsrc.lstrip('/').replace('/', '_')
    hostname = socket.gethostname()
    if ':' in src:
        label = f'{src}_{dt}'
    else:
        label = f'{hostname}_{src}_{dt}'
    return label


parser = argparse.ArgumentParser(description='Does rsync --list-dest backups, in the style if TimeMachine')
parser.add_argument('--debug', action='store_true', help='Turn on more log messages')
parser.add_argument('--demon', action='store_true', help='Do not output to console, only logfile')
parser.add_argument('--dryrun', action='store_true', help='do not actually do it, just say what would be done')
parser.add_argument('src', action='store', help='Directory to back up')
parser.add_argument('dest', action='store', help='Destination directory. This is the "root" directory of the backup structure, not the individual subdirectory. The script will create the latter itself.')

args = parser.parse_args()

logger = logging.getLogger()
logger.setLevel(logging.INFO)
formatter = logging.Formatter("%(asctime)s %(process)d:%(module)s:%(lineno)d %(levelname)s: %(message)s")
logfile = "cloud_backup.log"
filehandler = logging.handlers.RotatingFileHandler(logfile, backupCount=10, maxBytes=10000000)
streamhandler = logging.StreamHandler()
filehandler.setFormatter(formatter)
streamhandler.setFormatter(formatter)
logger.addHandler(filehandler)
if args.debug:
    logger.setLevel(logging.DEBUG)
if not args.demon:
    logger.addHandler(streamhandler)

# Remove trailing slash from src and dest
src = args.src.rstrip('/')
dest = args.dest.rstrip('/')

# Check destination for rsync_backup.marker file
marker = os.path.join(dest, 'rsync_backup.marker')
if not os.path.exists(marker):
    logger.error(f"No rsync_backup.marker file in {dest}. Touch this file to indicate this is a valid rsync_backup destination")
    exit(1)

# Check destination for allready running pid file
locked = False
pidfile = 'rsync_backup.pid'
pid = getfile(pidfile, dest)
if pid is not None:
    pid = int(pid)
    # pid file exists, but could be stale
    locked = True
    try:
        os.kill(pid, signal.SIGUSR1)
    except:
        # kill failed, that pid doesn't exist or is not ours.
        # pid file is stale
        locked = False
if(locked):
    logger.error(f'rsync_backup allready running at this destination: PID: {pid}')
    exit(2)

# Write pid file
putfile(pidfile, dest, str(os.getpid()))

# Get exclude option
excludefile = os.path.join(dest, 'rsync_backup.exclude')

# Get last good backup marker
lastgood = getfile('rsync_backup.lastgood', dest)
if lastgood is None:
    logger.info("No last good backup found, will do full backup")
else:
    logger.info(f"last good backup: {lastgood}")

# Get the label for this backup
label = get_label(src)
logger.info(f"Backup label is: {label}")

# Build rsync command
rsync = ['rsync', '-D', '--numeric-ids', '--links', '--hard-links', '--one-file-system', '--itemize-changes', '--times', '--perms', '--recursive', '--owner', '--group', '--stats', '--human-readable', '--quiet']

if args.dryrun:
    rsync.append('--dry-run')

if lastgood is not None:
    rsync.append(f'--link-dest={os.path.join(dest, lastgood)}')

if os.path.exists(excludefile):
    rsync.append(f'--exclude-from={excludefile}')
    logger.info(f'Exclude file: {excludefile}')

rsync.append(f'--log-file={os.path.join(dest, label)}.log')

rsync.append(src)
rsync.append(os.path.join(dest, label))

logger.debug("rsync command: %s", ' '.join(rsync))
retcode = run(rsync, logger)

if retcode == 0:
    putfile('rsync_backup.lastgood', dest, label)
    logger.info('rsync completed OK, updated lastgood')
else:
    logger.error('rsync FAILED. Not updating lastgood')

os.remove(os.path.join(dest, pidfile))
logger.info("All done. Exiting")
