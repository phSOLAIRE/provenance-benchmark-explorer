#!/bin/bash
# capture_proc_io.sh - Sample /proc/<pid>/io for all user processes on a login node.
#
# Captures per-process I/O syscall counts and byte volumes every INTERVAL seconds.
#
# Output: Hourly-rotated TSV files in OUT_DIR. One row per process per sample.
# run e.g. as: nohup bash ./capture_proc_io.sh > capture_io.log 2>&1 &

set -euo pipefail

# config
INTERVAL=300 # 5 min
DURATION=1209600 # 14 days
OUT_DIR="/mnt/lustre-grete/usr/u20606/capture_proc" # in work dir accessible for me
MIN_UID=0 # optionally set to skip system/service users, but would be good to captzre as well

DATE_CMD="/bin/date"
AWK_CMD="/usr/bin/awk"

# 
mkdir -p "$OUT_DIR"
echo $$ > /tmp/capture_proc_io.pid
START=$($DATE_CMD +%s)

# file rotation
current_outfile=""
get_outfile() {
    local hour_tag
    hour_tag=$($DATE_CMD +%Y%m%d_%H)
    local f="$OUT_DIR/io_${hour_tag}.tsv"
    if [ "$f" != "$current_outfile" ]; then
        current_outfile="$f"
        if [ ! -f "$f" ]; then
            printf "sample_ts\tpid\tuid\tcomm\tsyscr\tsyscw\tread_bytes\twrite_bytes\trchar\twchar\n" > "$f"
        fi
    fi
}

echo "$($DATE_CMD) - capture_proc_io.sh started, interval=${INTERVAL}s, duration=${DURATION}s, output=${OUT_DIR}/" >&2
echo "PID file: /tmp/capture_proc_io.pid ($$)" >&2

while true; do
    # duration limit
    ts=$($DATE_CMD +%s)
    if [ "$DURATION" -gt 0 ]; then
        elapsed=$((ts - START))
        if [ "$elapsed" -ge "$DURATION" ]; then
            echo "$($DATE_CMD) - Duration limit reached (${DURATION}s). Exiting." >&2
            break
        fi
    fi

    get_outfile

    buf=""
    collected=0
    skipped=0

    for proc_dir in /proc/[0-9]*; do
        pid="${proc_dir##*/}"

        uid=$($AWK_CMD '/^Uid:/ {print $2; exit}' "$proc_dir/status" 2>/dev/null) || { skipped=$((skipped+1)); continue; }

        # optinally skip users up to MIN_UID
        if [ "$MIN_UID" -gt 0 ] && [ "$uid" -lt "$MIN_UID" ] 2>/dev/null; then
            continue
        fi

        # short process name
        comm=$(tr -d '\n\t,' < "$proc_dir/comm" 2>/dev/null) || { skipped=$((skipped+1)); continue; }
        [ -z "$comm" ] && { skipped=$((skipped+1)); continue; }

        # parse /proc/pid/io
        io_fields=$($AWK_CMD '
            /^rchar:/       { rchar=$2 }
            /^wchar:/       { wchar=$2 }
            /^syscr:/       { syscr=$2 }
            /^syscw:/       { syscw=$2 }
            /^read_bytes:/  { rb=$2 }
            /^write_bytes:/ { wb=$2 }
            END { if (syscr != "" && syscw != "" && rb != "" && wb != "" && rchar != "" && wchar != "")
                      print syscr "\t" syscw "\t" rb "\t" wb "\t" rchar "\t" wchar;
                  else
                      print "INCOMPLETE" }
        ' "$proc_dir/io" 2>/dev/null) || { skipped=$((skipped+1)); continue; }

        # skip if process died mid-read
        [ "$io_fields" = "INCOMPLETE" ] && { skipped=$((skipped+1)); continue; }

        buf+="${ts}	${pid}	${uid}	${comm}	${io_fields}
"
        collected=$((collected+1))
    done

    # write to file
    if [ -n "$buf" ]; then
        printf '%s' "$buf" >> "$current_outfile" || \
            echo "Warning: Disk write failed at $ts" >&2
    fi

    # log
    scan_end=$($DATE_CMD +%s)
    scan_duration=$((scan_end - ts))
    echo "$($DATE_CMD -d @$ts '+%Y-%m-%d %H:%M:%S') - collected $collected processes, skipped $skipped, scan took ${scan_duration}s" >&2

    # sleep
    remaining=$((INTERVAL - scan_duration))
    if [ "$remaining" -gt 0 ]; then
        sleep "$remaining" || true
    else
        echo "Warning: Scan took longer than interval (${scan_duration}s > ${INTERVAL}s)" >&2
    fi
done

echo "$($DATE_CMD) - capture_proc_io.sh finished." >&2
rm -f /tmp/capture_proc_io.pid