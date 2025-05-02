#!/bin/bash

# Usage: ./aredn_bandwidth_test.sh node1 node2 [...] [-r NUM_RUNS] [-u] [-q]

set -e

# Default values
NUM_RUNS=1
VERBOSE=1
OUT_CSV=results_$(date '+%Y%m%d').csv
PROTOCOL=tcp
OUTDIR="aredn_results"

# Helper: verbose echo
vlog() {
    if [ "$VERBOSE" -eq 1 ]; then
        echo "$@"
    fi
}

# Parse arguments
NODES=()
while [[ $# -gt 0 ]]; do
    case "$1" in
    -r | --runs)
        NUM_RUNS="$2"
        shift 2
        ;;
    -q | --quiet)
        VERBOSE=0
        shift
        ;;
    -u | --udp)
        PROTOCOL=udp
        shift
        ;;
    -*)
        echo "Unknown option $1"
        exit 1
        ;;
    *)
        NODES+=("$1")
        shift
        ;;
    esac
done

if [ "${#NODES[@]}" -lt 2 ]; then
    echo "Please specify at least 2 node hostnames."
    exit 1
fi

vlog "Nodes: ${NODES[*]}"
vlog "Runs: $NUM_RUNS"
vlog "Output CSV: $OUT_CSV"

# Create the output CSV and add a header if it doesn't already exists
[[ -f $OUT_CSV ]] || echo "date,client,server,snr_dB,nsnr_dB,datarate_Mbps,iperf_speed_Mbps,iperf_retries,protocol" >$OUT_CSV

for ((run = 1; run <= NUM_RUNS; run++)); do
    vlog "Run $run/$NUM_RUNS"
    TIMESTAMP="$(date '+%Y%m%d_%H%M%S')"
    run_outdir="${OUTDIR}/${TIMESTAMP}"
    mkdir -p "$run_outdir"

    for NODE in "${NODES[@]}"; do
        URL="http://${NODE}.local.mesh:8080/a/u-local-and-neighbor-devices"
        vlog "Fetching neighbor info from $NODE"
        STATS_OUTFILE="$run_outdir/neighbor_stats_${NODE}.html"
        curl -s "$URL" -o "$STATS_OUTFILE"

        SRC=$NODE
        for DST in "${NODES[@]}"; do
            if [ "$SRC" != "$DST" ]; then
                vlog "Running iperf from $SRC to $DST"
                URL="http://${SRC}.local.mesh:8080/cgi-bin/iperf?server=${DST}.local.mesh&protocol=${PROTOCOL}"
                IPERF_OUTFILE="$run_outdir/iperf_${SRC}_${DST}.html"
                curl -s "$URL" -o "$IPERF_OUTFILE"
                # Process data and write results to CSV
                snr=$(grep 'icon wifi' ${STATS_OUTFILE} | grep $DST | cut -d ';' -f3 | cut -d '>' -f11 | cut -d '<' -f1 | tr -d '\n')
                nsnr=$(grep 'icon wifi' ${STATS_OUTFILE} | grep $DST | cut -d ';' -f3 | cut -d '>' -f13 | cut -d '<' -f1 | tr -d '\n')
                err_pct=$(grep 'icon wifi' ${STATS_OUTFILE} | grep $DST | cut -d ';' -f3 | cut -d '>' -f15 | cut -d '<' -f1 | tr -d '\n')
                data_rate=$(grep 'icon wifi' ${STATS_OUTFILE} | grep $DST | cut -d ';' -f3 | cut -d '>' -f17 | cut -d '<' -f1 | tr -d '\n')
                effective_bandwidth=$(grep sender ${IPERF_OUTFILE} | grep -oP '\d+.?\d*\sMbits/sec' |cut -d ' ' -f1)
                retries=$(grep sender ${IPERF_OUTFILE} | grep -oP "(\d+)\s+sender" | cut -d ' ' -f1)
                echo "${TIMESTAMP},${SRC},${DST},${snr},${nsnr},${data_rate},${effective_bandwidth},${retries},${PROTOCOL}" >>$OUT_CSV

            fi
        done
    done
done

echo "Bandwidth tests completed. Results saved in: $OUT_CSV. Raw data saved in $OUTDIR"
