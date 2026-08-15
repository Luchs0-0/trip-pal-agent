#!/bin/bash
# 把 5 帧截图 + 5 段配音合成为 demo 视频
set -e
FRAMES=frames
AUDIO=audio
OUT=demo_video.mp4

# 每段的时长 = 配音时长 + 0.8s 余量
declare -a DURS
DURS[1]=9.5
DURS[2]=11.0
DURS[3]=10.5
DURS[4]=7.5
DURS[5]=10.5

# 生成每段的视频片段（图片 + 无声）
for i in 1 2 3 4 5; do
  ffmpeg -y -loglevel error -loop 1 -i "$FRAMES/shot_${i}_"*.png -t "${DURS[$i]}" -r 30 \
    -vf "scale=1280:800,format=yuv420p,fade=t=in:st=0:d=0.4,fade=t=out:st=$(echo "${DURS[$i]} - 0.4" | bc):d=0.4" \
    -c:v libx264 -preset fast -pix_fmt yuv420p "/tmp/seg_$i.mp4"
  echo "segment $i done"
done

# 拼接视频段
cat > /tmp/concat.txt <<'EOF'
file '/tmp/seg_1.mp4'
file '/tmp/seg_2.mp4'
file '/tmp/seg_3.mp4'
file '/tmp/seg_4.mp4'
file '/tmp/seg_5.mp4'
