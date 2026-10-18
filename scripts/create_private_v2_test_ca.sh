#!/bin/sh
# Local test CA only. Never changes Android/device-wide/system trust.
set -eu
[ "$#" -eq 1 ] || { echo 'Usage: create_private_v2_test_ca.sh NEW_PRIVATE_DIRECTORY' >&2; exit 2; }
[ ! -e "$1" ] && [ ! -L "$1" ] || { echo 'Refusing existing output' >&2; exit 1; }
umask 077
mkdir "$1"
openssl req -x509 -newkey rsa:2048 -nodes -days 3 \
  -subj '/CN=Sugarglider Private V2 Staging CA' \
  -addext 'basicConstraints=critical,CA:TRUE,pathlen:0' \
  -addext 'keyUsage=critical,keyCertSign,cRLSign' -addext 'subjectKeyIdentifier=hash' \
  -keyout "$1/ca.key" -out "$1/ca.pem"
openssl req -newkey rsa:2048 -nodes -subj '/CN=localhost' \
  -keyout "$1/server.key" -out "$1/server.csr"
cat > "$1/server.ext" <<'EXT'
subjectAltName=DNS:localhost,IP:127.0.0.1
basicConstraints=critical,CA:FALSE
keyUsage=critical,digitalSignature,keyEncipherment
extendedKeyUsage=serverAuth
authorityKeyIdentifier=keyid,issuer
subjectKeyIdentifier=hash
EXT
openssl x509 -req -in "$1/server.csr" -CA "$1/ca.pem" -CAkey "$1/ca.key" \
  -CAcreateserial -days 3 -extfile "$1/server.ext" -out "$1/server.pem"
openssl verify -CAfile "$1/ca.pem" -x509_strict -verify_hostname localhost "$1/server.pem"
