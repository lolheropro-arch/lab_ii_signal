#!/bin/sh
# build.sh -- Linux version of build.bat:  ./build.sh 2   |   ./build.sh 0 3201
set -e
cd "$(dirname "$0")"
MODE=${1:-2}; PART=${2:-3202}
QBIN=$(ls -d "$HOME"/intelFPGA_lite/*/quartus/bin /opt/intelFPGA_lite/*/quartus/bin 2>/dev/null | tail -1)
[ -n "$QBIN" ] || { echo "Quartus not found: set QBIN"; exit 1; }
"$QBIN/quartus_sh" -t create_project.tcl "$MODE" "$PART"
"$QBIN/quartus_sh" --flow compile task3_audio
"$QBIN/quartus_pgm" -c 1 -m jtag -o "p;output_files/task3_audio.sof"
echo "DONE: LEDR0 should blink"
