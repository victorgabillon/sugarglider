#!/bin/sh
# Sourced by the independent map and routing builders. Never consume host-wide
# memory or CPU defaults merely because a production region is larger.
SUGARGLIDER_BUILD_MEMORY_MB=${SUGARGLIDER_BUILD_MEMORY_MB:-3072}
SUGARGLIDER_BUILD_CPUS=${SUGARGLIDER_BUILD_CPUS:-2}
case "$SUGARGLIDER_BUILD_MEMORY_MB" in
    ""|0*|*[!0-9]*) echo "Build limits must be positive integers without leading zeros" >&2; exit 2 ;;
esac
case "$SUGARGLIDER_BUILD_CPUS" in
    ""|0*|*[!0-9]*) echo "Build limits must be positive integers without leading zeros" >&2; exit 2 ;;
esac
if [ "${#SUGARGLIDER_BUILD_MEMORY_MB}" -gt 5 ] || [ "${#SUGARGLIDER_BUILD_CPUS}" -gt 2 ]; then
    echo "Build limits exceed their supported range" >&2
    exit 2
fi
if [ "$SUGARGLIDER_BUILD_MEMORY_MB" -lt 512 ] || [ "$SUGARGLIDER_BUILD_MEMORY_MB" -gt 32768 ] \
    || [ "$SUGARGLIDER_BUILD_CPUS" -lt 1 ] || [ "$SUGARGLIDER_BUILD_CPUS" -gt 16 ]; then
    echo "Build memory must be 512..32768 MiB and CPUs 1..16" >&2
    exit 2
fi
SUGARGLIDER_BUILD_JAVA_HEAP_MB=$((SUGARGLIDER_BUILD_MEMORY_MB * 3 / 4))
echo "Build limits: ${SUGARGLIDER_BUILD_MEMORY_MB} MiB, ${SUGARGLIDER_BUILD_CPUS} CPUs, no container swap" >&2
