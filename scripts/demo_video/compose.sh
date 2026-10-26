#!/usr/bin/env bash
# Compose the ACE Ops demo video: the product recording full-frame (1920x1080)
# with the presenters' camera take in a gold-ringed circle bottom-left, and the
# camera take's audio as the soundtrack.
#
#   scripts/demo_video/compose.sh CAMERA.mp4 [PRODUCT.mp4] [OUT.mp4] [OFFSET]
#
#   CAMERA.mp4   the single continuous take of the three presenters (with audio)
#   PRODUCT.mp4  default docs/pitch/product-demo.mp4 (from record_product.py)
#   OUT.mp4      default docs/pitch/aceops-demo.mp4
#   OFFSET       seconds to delay the product video (also the OFFSET env var):
#                use it when the presenters start talking before the screen should move.
#
# If the camera take is longer than the product video, the product's last frame
# is held; if it is shorter, the output is cut to the camera length.
# Works on macOS bash 3.2.
set -euo pipefail

usage() {
  echo "usage: $0 CAMERA.mp4 [PRODUCT.mp4] [OUT.mp4] [OFFSET]" >&2
  exit 2
}

[ $# -ge 1 ] || usage
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
CAMERA="$1"
PRODUCT="${2:-$ROOT/docs/pitch/product-demo.mp4}"
OUT="${3:-$ROOT/docs/pitch/aceops-demo.mp4}"
OFFSET="${4:-${OFFSET:-0}}"

FFMPEG="${FFMPEG:-$(command -v ffmpeg || true)}"
FFPROBE="${FFPROBE:-$(command -v ffprobe || true)}"
[ -n "$FFMPEG" ] || FFMPEG=/opt/homebrew/bin/ffmpeg
[ -n "$FFPROBE" ] || FFPROBE=/opt/homebrew/bin/ffprobe

[ -f "$CAMERA" ] || { echo "camera take not found: $CAMERA" >&2; exit 1; }
[ -f "$PRODUCT" ] || { echo "product video not found: $PRODUCT (run record_product.py first)" >&2; exit 1; }
case "$OFFSET" in
  ''|*[!0-9.]*) echo "OFFSET must be a number of seconds, got: $OFFSET" >&2; exit 1 ;;
esac

duration() {
  "$FFPROBE" -v error -show_entries format=duration -of default=nw=1:nk=1 "$1"
}
has_audio() {
  [ -n "$("$FFPROBE" -v error -select_streams a -show_entries stream=codec_type -of csv=p=0 "$1")" ]
}

CAM_DUR="$(duration "$CAMERA")"
PROD_DUR="$(duration "$PRODUCT")"
if ! has_audio "$CAMERA"; then
  echo "warning: $CAMERA has no audio stream; the output will be silent" >&2
fi

# Floating-point helpers (bash 3.2 has no float math).
PROD_END="$(awk -v p="$PROD_DUR" -v o="$OFFSET" 'BEGIN { printf "%.3f", p + o }')"
PAD="$(awk -v c="$CAM_DUR" -v e="$PROD_END" 'BEGIN { d = c - e; if (d < 0) d = 0; printf "%.3f", d }')"
OUT_DUR="$CAM_DUR"

printf 'camera   %s  %.1fs\n' "$CAMERA" "$CAM_DUR"
printf 'product  %s  %.1fs (offset %ss)\n' "$PRODUCT" "$PROD_DUR" "$OFFSET"
if awk -v p="$PAD" 'BEGIN { exit !(p > 0) }'; then
  printf 'holding the product'"'"'s last frame for %.1fs\n' "$PAD"
elif awk -v c="$CAM_DUR" -v e="$PROD_END" 'BEGIN { exit !(e > c) }'; then
  printf 'camera is shorter than the product: output cut to %.1fs\n' "$CAM_DUR"
fi

# Background: the product scaled/letterboxed to 1920x1080, optionally delayed
# (first frame held for OFFSET) and extended (last frame held for PAD).
BG="[0:v]scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1,fps=30"
if awk -v o="$OFFSET" 'BEGIN { exit !(o > 0) }'; then
  BG="$BG,tpad=start_mode=clone:start_duration=$OFFSET"
fi
if awk -v p="$PAD" 'BEGIN { exit !(p > 0) }'; then
  BG="$BG,tpad=stop_mode=clone:stop_duration=$PAD"
fi
BG="$BG[bg]"

# Camera bubble: crop to a centred square, 360x360, then one geq pass sets the
# alpha to a 180px disc (anti-aliased edge) and paints the outer 4px gold #e8c290.
R2="sqrt((X-180)*(X-180)+(Y-180)*(Y-180))"
CAM="[1:v]crop=w='min(iw,ih)':h='min(iw,ih)',scale=360:360,fps=30,format=rgba"
CAM="$CAM,geq=r='if(gt($R2,176),232,r(X,Y))':g='if(gt($R2,176),194,g(X,Y))':b='if(gt($R2,176),144,b(X,Y))':a='255*clip(180.5-$R2,0,1)'[cam]"

MIX="[bg][cam]overlay=x=48:y=H-360-48:format=auto[out]"
FILTER="$BG;$CAM;$MIX"

CMD=("$FFMPEG" -y -hide_banner -loglevel error -stats
  -i "$PRODUCT" -i "$CAMERA"
  -filter_complex "$FILTER"
  -map "[out]" -map "1:a?"
  -c:v libx264 -preset medium -crf 20 -pix_fmt yuv420p -r 30
  -c:a aac -b:a 192k -ar 48000
  -movflags +faststart -t "$OUT_DUR"
  "$OUT")

echo
echo "running:"
printf ' %q' "${CMD[@]}"
echo
echo
mkdir -p "$(dirname "$OUT")"
"${CMD[@]}"
echo
echo "wrote $OUT ($(duration "$OUT" | awk '{ printf "%.1f", $1 }')s)"
