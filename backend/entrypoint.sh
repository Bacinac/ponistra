#!/bin/sh
set -eu
for kept in blobs:/data/blobs backup:/backup wal:/wal; do
	if [ ! -w "${kept#*:}" ]; then
		echo "${kept#*:} is not writable by uid $(id -u): create volumes/${kept%%:*} owned by it" >&2
		exit 1
	fi
done
python manage.py migrate --noinput
exec "$@"
