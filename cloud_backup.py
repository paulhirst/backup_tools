import argparse
import os
import os.path
import subprocess
import shutil
import logging
import logging.handlers

def md5sum(file, logger=None):
    cmd = ['/usr/bin/md5sum', file]
    result = subprocess.run(cmd, capture_output=True)
    if result.returncode != 0:
        logger.info(f'md5sum failed on {file} in {dir}: {result.stderr}')
        exit(1)
    text = result.stdout.decode('ASCII')
    with open('md5sums.txt', 'a') as f:
        f.write(text)

def run(cmd, logger):
    ret = subprocess.run(cmd, capture_output=True)
    stdout = ret.stdout.decode('ASCII')
    stderr = ret.stderr.decode('ASCII')
    if ret.returncode == 0:
        logger.info(f'Appears to have completed sucessfully. {stdout}, {stderr}')
    else:
        logger.info(f'Failed with returncode {ret.returncode}: {stdout}, {stderr}')


def crypt(src, dest, passphrase, logger=None):
    cmd = ['gpg', '--batch', '--passphrase', passphrase, '--output', dest, '--symmetric', src]
    logger.info(f'Encrypting {src} into {dest}')
    run(cmd, logger)

def tocloud(filename, cloud, logger=None):
    cmd = ['rclone', 'copy', filename, cloud]
    logger.info(f'rcloud copy {filename} to {cloud}')
    run(cmd, logger)

parser = argparse.ArgumentParser(description='Encrypt/Decrypt all files in a directory to another directory')
parser.add_argument('--debug', action='store_true', help='Turn on more log messages')
parser.add_argument('--demon', action='store_true', help='Do not output to console, only logfile')
parser.add_argument('--dryrun', action='store_true', help='do not actually do it, just say what would be done')
parser.add_argument('--keepcache', action='store_true', help='Do not clear out the cache - leave for inspection')
parser.add_argument('--cachedir', action='store', help='directory to use as local cache. Also looks at CLOUDBACKUP_CACHE environment variable')
parser.add_argument('--passphrase', action='store', help='directory to use as local cache. Also looks at CLOUDBACKUP_PASSPHRASE environment variable')
parser.add_argument('src', action='store', help='Directory to read from')
parser.add_argument('dest', action='store', help='Directory to write to')

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


# Get the passphrase from environemnt or args
passphrase = None
env_pp = os.environ.get('CLOUDBACKUP_PASSPHRASE')
arg_pp = args.passphrase
passphrase = env_pp if env_pp else arg_pp if arg_pp else None
if passphrase is None:
    logger.error('No passphrase supplied. Cannot continue')
    exit(1)

# Get the cachedir from environemnt or args
cachedir = None
env_cd = os.environ.get('CLOUDBACKUP_CACHEDIR')
arg_cd = args.cachedir
cachedir = env_cd if env_cd else arg_cd if arg_cd else None
if cachedir is None:
    logger.error('No cachedir supplied. Cannot continue')
    exit(1)

# PID specific subdirectory in cachedir
pid = str(os.getpid())
cachedir = os.path.join(cachedir, pid)
if os.path.exists(cachedir):
    # Deliberately don't blow it away - something weird is happening...
    logger.error(f'Error: cachedirectory for this PID already exists: {cachedir}')
    exit(1)
logger.info(f'Using cachedir: {cachedir}')
os.mkdir(cachedir)
oldpwd = os.getcwd()
os.chdir(cachedir)

# OK, now loop through the files...
srcfiles = os.listdir(path=args.src)
srcfiles.sort()

i = 0
for srcfile in srcfiles:
    i += 1
    logger.info(f'Processing file {i} of {len(srcfiles)}: {srcfile}')
    # If it's an md5sums.txt file, skip it
    if srcfile == 'md5sums.txt':
        logger.info('skipping md5sums.txt file')
        continue
    # Figure out the destination filename
    destfile = srcfile + ".gpg"

    # Create the names with paths
    origfile = os.path.join(args.src, srcfile)

    # Copy the source file into the cache directory
    logger.info(f'Copying {origfile} to {srcfile}')
    shutil.copy2(origfile, srcfile)

    # md5 the cached srcfile
    logger.info(f'md5summing {srcfile}')
    md5sum(srcfile, logger=logger)

    # Do the encrypt, md5 the output
    crypt(srcfile, destfile, passphrase, logger=logger)
    logger.info(f'md5summing {destfile}')
    md5sum(destfile, logger=logger)

    # Delete the cache copy of the sourcfile
    if not args.keepcache:
        logger.info(f'deleting {srcfile} from {cachedir}')
        os.unlink(srcfile)

    # move the destfile to the cloud backup location
    if not args.dryrun:
        tocloud(destfile, args.dest, logger=logger)
    if not args.keepcache:
        logger.info(f'deleting {destfile} from {cachedir}')
        os.unlink(destfile)

# move the md5sum file to the cloud backup location
if not args.dryrun:
    tocloud('md5sums.txt', args.dest, logger=logger)
if not args.keepcache:
    os.unlink('md5sums.txt')

# cd back and Delete the cachedir
os.chdir(oldpwd)
if not args.keepcache:
    os.rmdir(cachedir)

