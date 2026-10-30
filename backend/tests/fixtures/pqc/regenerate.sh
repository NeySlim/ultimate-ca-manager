#!/bin/sh
# Regenerates the post-quantum fixtures with OpenSSL 3.5 or later. The tests
# read the files only: they never run openssl. Run from any directory.
set -eu
cd "$(dirname "$0")"

case "$(openssl version)" in
    "OpenSSL 3."[5-9]*|"OpenSSL 3."[1-9][0-9]*|"OpenSSL "[4-9]*) ;;
    *) echo "OpenSSL 3.5 or later is required: $(openssl version)" >&2; exit 1 ;;
esac

DAYS=36500
PASS=pqc-fixture   # PKCS#12 password, also in tests/pqc_fixtures.py

# One ML-DSA-65 key in the three PKCS#8 layouts OpenSSL writes: the seed alone
# (what pyca reads), seed and expanded key ("both", OpenSSL's default), and
# the expanded key alone.
openssl genpkey -algorithm ML-DSA-65 -provparam ml-dsa.output_formats=seed-only -out mldsa65-seed.pem
openssl pkey -in mldsa65-seed.pem -provparam ml-dsa.output_formats=seed-priv -out mldsa65-both.pem
openssl pkey -in mldsa65-seed.pem -provparam ml-dsa.output_formats=priv-only -out mldsa65-priv.pem

openssl req -new -key mldsa65-seed.pem -subj "/CN=UCM PQC fixture ML-DSA-65" -out mldsa65-csr.pem
openssl req -x509 -key mldsa65-seed.pem -subj "/CN=UCM PQC fixture ML-DSA-65" -days "$DAYS" \
    -addext "keyUsage=critical,digitalSignature,keyCertSign,cRLSign" -out mldsa65-cert.pem

openssl pkcs12 -export -inkey mldsa65-seed.pem -in mldsa65-cert.pem -name "UCM PQC fixture" \
    -passout "pass:$PASS" -out mldsa65.p12

# CMS SignedData signed with ML-DSA-65 over SHA-512 (RFC 9882), content attached
printf 'UCM post-quantum CMS fixture\n' > cms-content.txt
openssl cms -sign -binary -nodetach -md sha512 -signer mldsa65-cert.pem -inkey mldsa65-seed.pem \
    -in cms-content.txt -outform DER -out mldsa65-signed.cms

# SLH-DSA-SHA2-128s self-signed certificate (read-only in UCM: pyca cannot sign it)
openssl req -x509 -newkey SLH-DSA-SHA2-128s -nodes -keyout /dev/null \
    -subj "/CN=UCM PQC fixture SLH-DSA-SHA2-128s" -days "$DAYS" -out slhdsa-sha2-128s-cert.pem
