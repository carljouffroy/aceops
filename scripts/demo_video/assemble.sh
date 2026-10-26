#!/usr/bin/env bash
# Assemble the final ACE Ops demo (1920x1080, 30 fps) from three inputs:
#
#   scripts/demo_video/assemble.sh GB10.mp4 CAMERA.mp4 [OUT.mp4]
#
#   GB10.mp4    a clip of the GB10 box shot by a teammate (landscape or portrait
#               phone video). Shown FIRST, for its full length, with its own audio.
#               A portrait clip is fitted on the canvas over a blurred, filled copy
#               of itself; a landscape clip is letterboxed the same way.
#   CAMERA.mp4  the two presenters' camera take (landscape or portrait). Composited
#               as a gold-ringed circle bottom-left over BOTH segments from t=0
#               (OFFSET=seconds shifts it later). Its audio is used over the product
#               segment only, unless VOICE_OVER_GB10=1, which uses it throughout.
#   OUT.mp4     default docs/pitch/aceops-demo-final.mp4
#
# The product segment is docs/pitch/product-demo-60s.mp4 (PRODUCT=path to override),
# shown SECOND. Segments are joined with the concat filter (not the concat demuxer),
# so the sources may differ in size, frame rate and codec.
# Works on macOS bash 3.2.
set -euo pipefail

usage() {
  echo "usage: $0 GB10.mp4 CAMERA.mp4 [OUT.mp4]   (env: PRODUCT, OFFSET, VOICE_OVER_GB10=1)" >&2
  exit 2
}
[ $# -ge 2 ] || usage

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
GB10="$1"
CAMERA="$2"
OUT="${3:-$ROOT/docs/pitch/aceops-demo-final.mp4}"
PRODUCT="${PRODUCT:-$ROOT/docs/pitch/product-demo-60s.mp4}"
OFFSET="${OFFSET:-0}"
VOICE_OVER_GB10="${VOICE_OVER_GB10:-0}"

FFMPEG="${FFMPEG:-$(command -v ffmpeg || true)}"
FFPROBE="${FFPROBE:-$(command -v ffprobe || true)}"
[ -n "$FFMPEG" ] || FFMPEG=/opt/homebrew/bin/ffmpeg
[ -n "$FFPROBE" ] || FFPROBE=/opt/homebrew/bin/ffprobe

for f in "$GB10" "$CAMERA" "$PRODUCT"; do
  [ -f "$f" ] || { echo "input not found: $f" >&2; exit 1; }
done
case "$OFFSET" in
  ''|*[!0-9.]*) echo "OFFSET must be a number of seconds, got: $OFFSET" >&2; exit 1 ;;
esac

duration() { "$FFPROBE" -v error -show_entries format=duration -of default=nw=1:nk=1 "$1"; }
has_audio() { [ -n "$("$FFPROBE" -v error -select_streams a -show_entries stream=codec_type -of csv=p=0 "$1")" ]; }
fmt() { awk -v x="$1" 'BEGIN { printf "%.2f", x }'; }

GB10_DUR="$(duration "$GB10")"
PROD_DUR="$(duration "$PRODUCT")"
CAM_DUR="$(duration "$CAMERA")"
TOTAL="$(awk -v a="$GB10_DUR" -v b="$PROD_DUR" 'BEGIN { printf "%.3f", a + b }')"

echo "inputs:"
printf '  gb10     %-60s %7ss%s\n' "$GB10" "$(fmt "$GB10_DUR")" "$(has_audio "$GB10" || echo '  (no audio)')"
printf '  product  %-60s %7ss\n' "$PRODUCT" "$(fmt "$PROD_DUR")"
printf '  camera   %-60s %7ss%s\n' "$CAMERA" "$(fmt "$CAM_DUR")" "$(has_audio "$CAMERA" || echo '  (no audio)')"
printf '  offset   %ss   voice over gb10: %s\n' "$OFFSET" "$VOICE_OVER_GB10"
printf 'output length %ss (gb10 + product)\n' "$(fmt "$TOTAL")"
if awk -v c="$CAM_DUR" -v o="$OFFSET" -v t="$TOTAL" 'BEGIN { exit !(c + o < t) }'; then
  echo "note: the camera take ends $(awk -v c="$CAM_DUR" -v o="$OFFSET" -v t="$TOTAL" 'BEGIN { printf "%.1f", t - c - o }')s before the video does; the bubble holds its last frame" >&2
fi

# --- segment A: GB10 clip on a blurred fill ------------------------------------
# A blurred copy fills 1920x1080 (cropped), the clip itself is scaled to fit inside
# the canvas (height 1080 for portrait, width 1920 for a wide landscape) and centred.
SEG_A="[0:v]split=2[a_bg_src][a_fg_src];"
SEG_A="$SEG_A[a_bg_src]scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,gblur=sigma=28,eq=brightness=-0.08[a_bg];"
SEG_A="$SEG_A[a_fg_src]scale=1920:1080:force_original_aspect_ratio=decrease[a_fg];"
SEG_A="$SEG_A[a_bg][a_fg]overlay=(W-w)/2:(H-h)/2:format=auto,setsar=1,fps=30,format=yuv420p[segA]"

# --- segment B: product recording, letterboxed ---------------------------------
SEG_B="[1:v]scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1,fps=30,format=yuv420p[segB]"

# --- audio: A's own audio (or camera) then camera over B -----------------------
# Each segment's audio is cut/padded to exactly its video length so concat stays in sync.
A_AUDIO_SRC="[0:a]"
if [ "$VOICE_OVER_GB10" = "1" ]; then
  A_AUDIO_SRC="[2:a]"
fi
if [ "$VOICE_OVER_GB10" != "1" ] && ! has_audio "$GB10"; then
  echo "warning: $GB10 has no audio; segment A will be silent (set VOICE_OVER_GB10=1 to use the camera audio)" >&2
  A_AUDIO_SRC="anullsrc=channel_layout=stereo:sample_rate=48000,"
  AUD_A="${A_AUDIO_SRC}atrim=0:$GB10_DUR,asetpts=PTS-STARTPTS[audA]"
else
  if [ "$VOICE_OVER_GB10" = "1" ]; then
    # camera audio from t=0 (shifted by OFFSET), cut to the length of A
    AUD_A="[2:a]adelay=$(awk -v o="$OFFSET" 'BEGIN { printf "%d", o * 1000 }')|$(awk -v o="$OFFSET" 'BEGIN { printf "%d", o * 1000 }'),apad,atrim=0:$GB10_DUR,asetpts=PTS-STARTPTS,aformat=sample_rates=48000:channel_layouts=stereo[audA]"
  else
    AUD_A="[0:a]apad,atrim=0:$GB10_DUR,asetpts=PTS-STARTPTS,aformat=sample_rates=48000:channel_layouts=stereo[audA]"
  fi
fi
if has_audio "$CAMERA"; then
  # camera audio for B is the part of the take that plays while B is on screen:
  # from GB10_DUR-OFFSET to GB10_DUR-OFFSET+PROD_DUR on the camera's clock.
  CAM_B_START="$(awk -v g="$GB10_DUR" -v o="$OFFSET" 'BEGIN { s = g - o; if (s < 0) s = 0; printf "%.3f", s }')"
  CAM_B_END="$(awk -v s="$CAM_B_START" -v p="$PROD_DUR" 'BEGIN { printf "%.3f", s + p }')"
  AUD_B="[2:a]apad,atrim=$CAM_B_START:$CAM_B_END,asetpts=PTS-STARTPTS,aformat=sample_rates=48000:channel_layouts=stereo[audB]"
else
  echo "warning: $CAMERA has no audio; the product segment will be silent" >&2
  AUD_B="anullsrc=channel_layout=stereo:sample_rate=48000,atrim=0:$PROD_DUR,asetpts=PTS-STARTPTS[audB]"
fi
AUDIO="$AUD_A;$AUD_B;[audA][audB]concat=n=2:v=0:a=1[aout]"

# --- camera bubble over the whole video ----------------------------------------
# Centre-square crop, 360x360, alpha disc of radius 180 with a 4px gold (#e8c290) ring.
# tpad clones the first frame for OFFSET and the last frame to the end of the video.
R2="sqrt((X-180)*(X-180)+(Y-180)*(Y-180))"
CAM="[2:v]crop=w='min(iw,ih)':h='min(iw,ih)',scale=360:360,fps=30,format=rgba"
CAM="$CAM,geq=r='if(gt($R2,176),232,r(X,Y))':g='if(gt($R2,176),194,g(X,Y))':b='if(gt($R2,176),144,b(X,Y))':a='255*clip(180.5-$R2,0,1)'"
if awk -v o="$OFFSET" 'BEGIN { exit !(o > 0) }'; then
  CAM="$CAM,tpad=start_mode=clone:start_duration=$OFFSET"
fi
CAM="$CAM,tpad=stop_mode=clone:stop_duration=$TOTAL[cam]"

JOIN="[segA][segB]concat=n=2:v=1:a=0[main]"
MIX="[main][cam]overlay=x=48:y=H-360-48:format=auto:eof_action=repeat[vout]"
FILTER="$SEG_A;$SEG_B;$JOIN;$CAM;$MIX;$AUDIO"

CMD=("$FFMPEG" -y -hide_banner -loglevel error -stats
  -i "$GB10" -i "$PRODUCT" -i "$CAMERA"
  -filter_complex "$FILTER"
  -map "[vout]" -map "[aout]"
  -c:v libx264 -preset medium -crf 20 -pix_fmt yuv420p -r 30
  -c:a aac -b:a 192k -ar 48000
  -movflags +faststart -t "$TOTAL"
  "$OUT")

echo
echo "running:"
printf ' %q' "${CMD[@]}"
echo
echo
mkdir -p "$(dirname "$OUT")"
"${CMD[@]}"
echo
echo "wrote $OUT ($(fmt "$(duration "$OUT")")s)"
