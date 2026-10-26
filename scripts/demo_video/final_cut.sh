#!/usr/bin/env bash
# ACE Ops · final demo cut.  1920x1080 · 30 fps · H.264 yuv420p / AAC 48 kHz stereo · 75 s.
#
#   scripts/demo_video/final_cut.sh [OUT.mp4]
#   env: PREVIEW=1 (fast, low quality render to out/final_cut/preview.mp4), CAMERA, GB10,
#        PRODUCT, SEGMENTS, MUSIC, COPY (second copy of the output; "" to skip), PY (python3
#        with Pillow, used by render_cards.py because this ffmpeg has no drawtext).
#
# Master clock: the presenters' camera take (67.07 s), played in full and unaltered, from
# t = 3.0 s.  Structure (output seconds):
#    0.00 –  3.00  title card: social-preview art on a blurred fill, 0.5 s fade in; music in
#    3.00 – 70.07  body: background video + presenters' circle (bottom-left) + their audio
#                  body  0–19 s   three shots of the GB10 footage (nvidia-smi, sandbox, board)
#                  body 19–67 s   ten jump cuts of the product recording, one per tour step
#                                 2–11, each starting 0.4 s into its step; lower thirds
#   70.07 – 75.00  end card (wordmark + links); music fades out over the last 2 s; 0.5 s to black
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"            # scripts/demo_video
ROOT="$(cd "$HERE/../.." && pwd)"                 # aceops
GB="$(cd "$ROOT/.." && pwd)"                      # GB10

FFMPEG="${FFMPEG:-/opt/homebrew/bin/ffmpeg}"
FFPROBE="${FFPROBE:-/opt/homebrew/bin/ffprobe}"
PY="${PY:-/opt/anaconda3/bin/python3}"

CAMERA="${CAMERA:-$GB/ACE Ops record.mov}"
GB10="${GB10:-$GB/WhatsApp Video 2026-10-25 at 17.16.20.mp4}"
PRODUCT="${PRODUCT:-$ROOT/docs/pitch/product-demo-60s.mp4}"
SEGMENTS="${SEGMENTS:-$ROOT/docs/pitch/product-demo-60s.segments.json}"
MUSIC="${MUSIC:-/private/tmp/claude-501/-Users-moorthy-Downloads-Projects-GB10/17b05545-4853-4e8d-9433-26342721904b/scratchpad/music/Inspired.mp3}"
ART="$ROOT/docs/assets/social-preview.png"
OUT="${1:-$ROOT/docs/pitch/aceops-demo-final.mp4}"
COPY="${COPY-$GB/ACE-Ops-demo.mp4}"
WORK="$HERE/out/final_cut"
PREVIEW="${PREVIEW:-0}"

for f in "$CAMERA" "$GB10" "$PRODUCT" "$SEGMENTS" "$MUSIC" "$ART"; do
  [ -f "$f" ] || { echo "input not found: $f" >&2; exit 1; }
done
mkdir -p "$WORK"

calc() { awk "BEGIN { printf \"%.4f\", $1 }"; }
duration() { "$FFPROBE" -v error -show_entries format=duration -of default=nw=1:nk=1 "$1"; }

# --- timing -------------------------------------------------------------------
TITLE=3.0                                   # title card; the body (camera clock) starts here
TOTAL=75.0
CAM_DUR="$(duration "$CAMERA")"             # 67.070125
CAM_A_START="$("$FFPROBE" -v error -select_streams a:0 -show_entries stream=start_time -of default=nw=1:nk=1 "$CAMERA")"
BODY="$CAM_DUR"
END_START="$(calc "$TITLE + $BODY")"        # 70.07
END_LEN="$(calc "$TOTAL - $END_START")"     # 4.93
DELAY_MS="$(awk -v t="$TITLE" -v a="$CAM_A_START" 'BEGIN { printf "%d", (t + a) * 1000 + 0.5 }')"

# --- captions + end card (PNG, rendered with Pillow) ---------------------------
"$PY" -I "$HERE/render_cards.py" "$WORK" "$ART" > "$WORK/cards.txt"

# --- shot list: source pad, in-point (s), length (s) ---------------------------
# GB10 footage, three shots; then one window per tour step 2..11 of the product cut,
# starting 0.4 s after the step's start. The last window is stretched by the few
# frames needed to reach the end of the camera audio (67.07 - 67.0).
SRC=(); INP=(); LEN=()
shot() { SRC+=("$1"); INP+=("$2"); LEN+=("$3"); }
shot g1 0  7
shot g2 14 6
shot g3 32 6
LENS=(4.0 4.2 4.8 5.2 3.6 6.0 4.6 4.6 5.4 5.6)
STEP_STARTS="$("$PY" -I -c 'import json,sys; d=json.load(open(sys.argv[1])); print(" ".join("%.3f" % s["start"] for s in d if 2 <= s["step"] <= 11))' "$SEGMENTS")"
i=0
for st in $STEP_STARTS; do
  len="${LENS[$i]}"
  [ "$i" -eq 9 ] && len="$(calc "$len + ($BODY - 67.0)")"
  shot "p$((i + 1))" "$(calc "$st + 0.4")" "$len"
  i=$((i + 1))
done
N=${#SRC[@]}

# --- filter graph --------------------------------------------------------------
FILTER="$WORK/filter.txt"
: > "$FILTER"
add() { printf '%s\n' "$1" >> "$FILTER"; }
V="fps=30,format=yuv420p,setsar=1"

# inputs: 0 art (title) · 1..N the shots, each seeked and cut on the input side (-ss/-t,
# so nothing is decoded twice or queued) · then camera, music, end card, disc, ring and
# the N caption PNGs
I_CAM=$((N + 1)); I_MUS=$((N + 2)); I_END=$((N + 3)); I_DISC=$((N + 4)); I_RING=$((N + 5)); I_CAP0=$((N + 6))

# title card: the art without its letterbox bars over a blurred, stretched copy of itself
add "[0:v]crop=1280:512:0:64,split=2[t_bg][t_fg];"
add "[t_bg]scale=1920:1080,gblur=sigma=40,eq=brightness=-0.06[t_bgb];"
add "[t_fg]scale=1920:768:flags=lanczos[t_fgs];"
add "[t_bgb][t_fgs]overlay=0:156,$V,trim=0:$TITLE,setpts=PTS-STARTPTS,fade=t=in:st=0:d=0.5[title];"

# body background: hard-cut shots, concatenated
CAP_S=(); CAP_E=(); cum=0; chain=""
for ((k = 0; k < N; k++)); do
  add "[$((k + 1)):v]scale=1920:1080:flags=lanczos,$V,trim=0:${LEN[$k]},setpts=PTS-STARTPTS[s$k];"
  CAP_S+=("$cum"); cum="$(calc "$cum + ${LEN[$k]}")"; CAP_E+=("$cum")
  chain="$chain[s$k]"
done
add "${chain}concat=n=$N:v=1:a=0[bodybg];"

# presenters: centre square of the take -> 380 px disc (alphamerge with disc.png) with a
# 5 px gold ring (#e8c290, ring.png) on its edge. (A geq-drawn disc works too but runs at
# ~4 fps; the pre-rendered masks keep the whole render fast.)
add "[$I_DISC:v]format=gray[disc];"
add "[$I_RING:v]format=rgba[ring];"
add "[$I_CAM:v]fps=30,setpts=PTS-STARTPTS,crop=720:720:280:0,scale=380:380:flags=lanczos,format=rgba[camsq];"
add "[camsq][disc]alphamerge[camd];"
add "[camd][ring]overlay=0:0:format=rgb:eof_action=repeat,format=rgba,fade=t=in:st=0:d=0.4:alpha=1[cam];"
add "[bodybg][cam]overlay=x=48:y=652:eof_action=repeat[b0];"

# lower thirds, bottom-right, one per shot, 0.3 s fade in / 0.2 s fade out
prev="b0"
for ((k = 0; k < N; k++)); do
  s="${CAP_S[$k]}"; e="$(calc "${CAP_E[$k]} - 0.05")"; fo="$(calc "$e - 0.2")"
  add "[$((I_CAP0 + k)):v]format=rgba,fade=t=in:st=$s:d=0.3:alpha=1,fade=t=out:st=$fo:d=0.2:alpha=1[c$k];"
  add "[$prev][c$k]overlay=x=W-w-48:y=H-138:enable='between(t,$s,$e)'[b$((k + 1))];"
  prev="b$((k + 1))"
done

# end card, fading to black over its last 0.5 s; then title + body + end card
add "[$I_END:v]$V,trim=0:$END_LEN,setpts=PTS-STARTPTS,fade=t=out:st=$(calc "$END_LEN - 0.5"):d=0.5[endc];"
add "[title][$prev][endc]concat=n=3:v=1:a=0[vout];"

# audio: voice (highpass, limiter) from t=3.0 at its own start offset; music 0.35 on the
# cards, 0.14 under the body and ducked a further ~8 dB while someone speaks
ES="$END_START"
ENV="if(lt(t,2.6),0.35,if(lt(t,3.4),0.35+(0.14-0.35)*(t-2.6)/0.8,if(lt(t,$ES-0.3),0.14,if(lt(t,$ES+0.5),0.14+(0.35-0.14)*(t-($ES-0.3))/0.8,0.35))))"
add "[$I_CAM:a]aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo,asetpts=PTS-STARTPTS,highpass=f=80,alimiter=limit=0.95:level=0,adelay=$DELAY_MS|$DELAY_MS,apad=whole_dur=$TOTAL,asplit=2[v_mix][v_sc];"
add "[$I_MUS:a]aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo,atrim=0:$TOTAL,asetpts=PTS-STARTPTS,afade=t=in:st=0:d=1,volume='$ENV':eval=frame,afade=t=out:st=$(calc "$TOTAL - 2"):d=2[m_env];"
add "[m_env][v_sc]sidechaincompress=threshold=0.04:ratio=4:attack=15:release=350:makeup=1[m_duck];"
add "[v_mix][m_duck]amix=inputs=2:duration=first:dropout_transition=0:normalize=0,alimiter=limit=0.97:level=0[aout]"

# --- render ----------------------------------------------------------------------
CMD=("$FFMPEG" -y -hide_banner -loglevel error -stats
  -loop 1 -framerate 30 -t "$TITLE" -i "$ART")
for ((k = 0; k < N; k++)); do
  case "${SRC[$k]}" in g*) src="$GB10" ;; *) src="$PRODUCT" ;; esac
  CMD+=(-ss "${INP[$k]}" -t "$(calc "${LEN[$k]} + 0.5")" -i "$src")
done
CMD+=(-i "$CAMERA" -i "$MUSIC"
  -loop 1 -framerate 30 -t "$END_LEN" -i "$WORK/endcard.png"
  -loop 1 -framerate 30 -t "$(calc "$BODY + 1")" -i "$WORK/disc.png"
  -loop 1 -framerate 30 -t "$(calc "$BODY + 1")" -i "$WORK/ring.png")
for ((k = 0; k < N; k++)); do
  CMD+=(-loop 1 -framerate 30 -t "$(calc "$BODY + 1")" -i "$WORK/$(printf 'cap-%02d.png' $((k + 1)))")
done
LIMIT="${LIMIT:-$TOTAL}"                       # LIMIT=seconds renders only the first part (tests)
if [ "$PREVIEW" = "1" ]; then
  OUT="$WORK/preview.mp4"; COPY=""
  ENC=(-c:v libx264 -preset ultrafast -crf 28)
else
  ENC=(-c:v libx264 -preset medium -crf 20)
fi
CMD+=(-filter_complex_script "$FILTER" -map "[vout]" -map "[aout]"
  "${ENC[@]}" -pix_fmt yuv420p -r 30
  -c:a aac -b:a 192k -ar 48000 -movflags +faststart -t "$LIMIT" "$OUT")

echo "shots (body-relative seconds):"
for ((k = 0; k < N; k++)); do
  printf '  %2d  %-3s in %7.3f  len %5.2f  body %6.2f - %6.2f\n' $((k + 1)) "${SRC[$k]}" "${INP[$k]}" "${LEN[$k]}" "${CAP_S[$k]}" "${CAP_E[$k]}"
done
echo "title $TITLE s · body $BODY s (voice delayed $DELAY_MS ms) · end card $END_LEN s from $END_START · total $TOTAL s"
mkdir -p "$(dirname "$OUT")"
"${CMD[@]}"
echo "wrote $OUT ($(duration "$OUT") s)"
if [ -n "$COPY" ]; then cp "$OUT" "$COPY"; echo "copied to $COPY"; fi

# --- verify ----------------------------------------------------------------------
"$FFPROBE" -v error -show_entries format=duration:stream=codec_type,codec_name,width,height,r_frame_rate,sample_rate,channels -of compact "$OUT"
for t in 1.5 8 25 40 60 72; do
  awk -v t="$t" -v l="$LIMIT" 'BEGIN { exit !(t < l) }' || continue
  "$FFMPEG" -v error -y -ss "$t" -i "$OUT" -frames:v 1 "$HERE/out/final-$t.png"
done
echo "frames: $HERE/out/final-{1.5,8,25,40,60,72}.png"
