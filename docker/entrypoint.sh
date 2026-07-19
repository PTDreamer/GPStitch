#!/bin/bash
set -e

# ---------------------------------------------------------------------------
# gopro-toolkit entrypoint
#
# Default: launches GPStitch web UI on port 8000
# Override: pass a CLI tool name as the first argument
#
# Examples:
#   docker run -p 8000:8000 gopro-toolkit
#   docker run -v $(pwd):/work gopro-toolkit gopro-dashboard.py --gpx ride.gpx input.MP4 out.MP4
#   docker run -v $(pwd):/work gopro-toolkit gopro-to-gpx.py input.MP4
# ---------------------------------------------------------------------------

ALL_TOOLS=(
    gpstitch
    gpstitch-dashboard
    gopro-dashboard.py
    gopro-cut.py
    gopro-extract.py
    gopro-to-gpx.py
    gopro-to-csv.py
    gopro-join.py
    gopro-rename.py
    gopro-layout.py
    gopro-contrib-data-extract.py
    gopro-debug.py
)

show_help() {
    echo ""
    echo "gopro-toolkit — GPStitch web UI + gopro-dashboard-overlay CLI"
    echo ""
    echo "Usage:"
    echo "  docker run -p 8000:8000 gopro-toolkit              Start the web UI (default)"
    echo "  docker run gopro-toolkit <command> [args...]        Run a CLI tool"
    echo ""
    echo "Available CLI tools:"
    for t in "${ALL_TOOLS[@]}"; do
        [ "$t" = "gpstitch" ] && continue
        echo "  $t"
    done
    echo ""
    echo "Volumes:"
    echo "  Mount your video/GPX files into /work"
    echo "    -v \$(pwd):/work"
    echo ""
}

# If no arguments (or just default CMD "gpstitch"), start the web server
if [ "$#" -eq 0 ] || [ "$1" = "gpstitch" ]; then
    # If CMD was just "gpstitch" and we consumed it, shift
    [ "$1" = "gpstitch" ] && shift

    echo "=== gopro-toolkit ==="
    echo "Starting GPStitch web UI..."
    echo "Open http://localhost:8000 in your browser"
    echo ""
    exec gpstitch "$@"
fi

# If first argument is a known tool, run it with UID/GID mapping
PROGRAM="$1"
shift

# Check if it's a known tool
FOUND=false
for t in "${ALL_TOOLS[@]}"; do
    if [ "$PROGRAM" = "$t" ]; then
        FOUND=true
        break
    fi
done

if [ "$FOUND" = "false" ]; then
    echo "Error: Unknown command '$PROGRAM'"
    show_help
    exit 1
fi

# Check the tool exists in the venv
if [ ! -e "/venv/bin/$PROGRAM" ]; then
    echo "Error: '$PROGRAM' not found in PATH"
    show_help
    exit 1
fi

# UID/GID mapping — run as the host user so mounted files have correct ownership
uid=$(ls -ldn /work 2>/dev/null | awk '{print $3}')
gid=$(ls -ldn /work 2>/dev/null | awk '{print $4}')

if [ -n "$uid" ] && [ "$uid" -ne 0 ]; then
    getent group "$gid" > /dev/null 2>&1 || groupadd -g "$gid" -f dash

    if ! getent passwd "$uid" > /dev/null 2>&1; then
        useradd --home-dir /home/dash --create-home --no-user-group \
            --uid "$uid" --gid "$gid" dash 2>/dev/null || true
        chown "$uid:$gid" /home/dash 2>/dev/null || true
    fi

    umask 0002
    exec sudo -u "#$uid" -H -E env PATH="$PATH" /venv/bin/$PROGRAM "$@"
else
    exec /venv/bin/$PROGRAM "$@"
fi
