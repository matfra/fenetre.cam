#!/bin/bash
flags_available="$(/usr/bin/ffmpeg 2>&1)";
flags_required="--enable-gpl --enable-postproc --enable-swscale --enable-avfilter --enable-libmp3lame --enable-libvorbis --enable-libtheora --enable-libx264 --enable-libspeex --enable-shared --enable-pthreads --enable-libopenjpeg --enable-libfaac --enable-nonfree";
for flag in ${flags_required}; do
     echo "${flags_available}" | grep -sq -- "${flag}"; printf -- "$?\t${flag}\n";
done
