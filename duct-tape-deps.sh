#!/bin/bash -eu

set -o pipefail

BASE_DIR="$PWD"

PYPY_DIR=/usr/lib/tklbam-pypy2
PYPY_BIN="$PYPY_DIR/bin"
PYPY_CMD="$PYPY_BIN/pypy"

DEPROOT_LIB="$BASE_DIR/deps/lib"
DEPROOT_BIN="$BASE_DIR/deps/bin"

TMP="$BASE_DIR/debian/tmp/tklbam-deps"

export LD_LIBRARY_PATH="$PYPY_BIN"

APP=$(basename "$0")
info() { echo "[$APP] INFO: $*"; }
fatal() { echo "[$APP] ERROR: $*" >&2; exit 1; }
ch_dir() { cd "$1" || fatal "cd $1 failed"; }

input_cache="${XDG_CACHE_HOME:+$XDG_CACHE_HOME/tklbam-build-inputs}"
input_cache="${input_cache:-$TMP/downloads}"
mkdir -p "$input_cache" "$TMP" "$DEPROOT_LIB" "$DEPROOT_BIN"
input_cache=$(realpath "$input_cache")
download=$(mktemp -d "$input_cache/.download.XXXXXX")
trap 'rm -rf -- "$download"' EXIT

info "Preparing pinned TurnKey dependencies"
while IFS= read -r line; do
    ch_dir "$TMP"
    pkg="${line%:*}"
    commit_id="${line##*:}"
    [[ "$pkg" =~ ^[a-z0-9-]+$ && "$commit_id" =~ ^[0-9a-f]{40}$ ]] ||
        fatal "Invalid dependency pin: $line"
    org=turnkeylinux
    if [[ "$pkg" == tklbam-duplicity ]]; then
        org=JedMeister
    fi
    cached="$input_cache/$pkg-$commit_id.git"
    if [[ ! -d "$cached" ]]; then
        info "Fetching $pkg at $commit_id"
        git init -q --bare "$download/repo"
        git -C "$download/repo" fetch --quiet --depth=1 \
            "https://github.com/$org/$pkg" "$commit_id"
        [[ $(git -C "$download/repo" rev-parse 'FETCH_HEAD^{commit}') == "$commit_id" ]] ||
            fatal "Unexpected commit for $pkg"
        if ! mv -T "$download/repo" "$cached"; then
            [[ -d "$cached" ]] || fatal "Unable to save $pkg in the build cache"
            rm -rf -- "$download/repo"
        fi
    else
        info "Using cached $pkg at $commit_id"
    fi
    mkdir "$pkg"
    git -C "$cached" archive "$commit_id" | tar -xf - -C "$pkg"
    ch_dir "$pkg"
    case "$pkg" in
        python-dateutil)
            mv "dateutil" "$DEPROOT_LIB/"
            ;;
        python-six)
            mv "six.py" "$DEPROOT_LIB/"
            ;;
        *)
            "$PYPY_CMD" setup.py build
            mv "build/lib"*/* "$DEPROOT_LIB/"
            ;;&
        tklbam-duplicity)
            mv "build/scripts-2.7/duplicity" "$DEPROOT_BIN/"
            ;;
    esac
done < "$BASE_DIR/dep-commit-ids"

ch_dir "$TMP"
read -r pycrypto_checksum pycrypto_archive <<< "$(
    sed -En '\|^[a-z0-9]+|p' "$BASE_DIR/pycryptodome.checksum.txt"
)"
[[ "$pycrypto_checksum" =~ ^[0-9a-f]{64}$ && "$pycrypto_archive" =~ ^v[0-9.]+[.]tar[.]gz$ ]] ||
    fatal "Invalid PyCryptodome source pin"
verified_pycrypto="${pycrypto_archive%.tar.gz}"
cached="$input_cache/$pycrypto_checksum-$pycrypto_archive"
verify_archive() {
    printf '%s  %s\n' "$pycrypto_checksum" "$1" | sha256sum -c --status
}
if [[ -f "$cached" ]] && verify_archive "$cached"; then
    info "Using cached PyCryptodome $verified_pycrypto"
else
    info "Fetching PyCryptodome $verified_pycrypto"
    url=https://github.com/Legrandin/pycryptodome/archive/refs/tags
    curl --fail --location --silent --show-error --output "$download/archive" \
        "$url/$pycrypto_archive"
    verify_archive "$download/archive" || fatal "$pycrypto_archive checksum mismatch"
    mv -fT "$download/archive" "$cached"
fi

build_dir="pycryptodome-${verified_pycrypto#v}"
info "Unpacking $pycrypto_archive and building pycryptodome $verified_pycrypto"
tar xf "$cached"
ch_dir "$build_dir"
"$LD_LIBRARY_PATH/pypy" setup.py build
ch_dir "$TMP"
mv "$build_dir/build/lib"*/* "$DEPROOT_LIB/"
info "TKLBAM dependencies built successfully"
