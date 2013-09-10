#!/bin/bash -x

error() {
	echo "error: $1"
	exit 1
}

dumpdb() {
    rm -rf $1
    mkdir -p $1
    su postgres -c "pg_dump -Ft $1" | tar xvC $1 > $1/manifest.txt
}

if [ -z "$1" ]; then
	echo "syntax: $0 path/to/output/"
	exit 1
fi

outdir=$1
mkdir -p $outdir
cd $outdir

databases=$(su postgres -c 'psql -l' | perl -ne 'if(/^ (\S+?)\s/) { print "$1\n" }' | grep -v template[0-9] | grep -v postgres)
for database in $databases; do
	dumpdb $database
done
su postgres -c "pg_dumpall --globals" > .globals.sql
