#!/bin/bash -x

error() {
	echo "error: $1"
	exit 1
}

restoredb() {
        su postgres -c "dropdb $1"

        cd $1
        tar c $(cat manifest.txt) 2>/dev/null | \
                pg_restore --create --format=tar | \
                #su postgres -c "psql --quiet --echo-all"
                su postgres -c "psql"

        cd ../
}

if [ -z "$1" ]; then
	echo "syntax: $0 path/to/pgfs/"
	exit 1
fi

outdir=$1
cd $outdir

#cat .globals.sql | su postgres -c 'psql -q -o /dev/null'
cat .globals.sql | su postgres -c 'psql -q -o /dev/null'
for d in *; do
	restoredb $d
done
