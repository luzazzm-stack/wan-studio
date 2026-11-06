#!/usr/bin/env bash
# Makes a contact sheet (one frame per second) of a video so it can be eyeballed: sheet.sh in.mp4 out.png
ffmpeg -v error -y -i "$1" -vf "fps=1,scale=360:-1,tile=6x1:padding=4" -frames:v 1 "$2" && ffprobe -v error -show_entries stream=width,height,r_frame_rate,nb_frames,codec_name -of csv=p=0 "$1"
