#!/bin/sh

PROFILE_SECONDS=${PROFILE_SECONDS:-30}
PROFILE_BUCKET=${PROFILE_BUCKET:-noon-core-profile-796cf65209c9ec825a36656712d6f54c}
PROFILE_RATE=${PROFILE_RATE:-20}
PROFILE_FILENAME=$(echo svg/`date +%Y%m%d`/`hostname`/`date +%s`.svg)
PROFILE_PID=$(ps aux | grep python3 | grep -vE 'timeout|grep|make'| head -n 2|head -n 1| tr -s " " | cut -f 2 -d" ")
cd /tmp && py-spy --flame profile.svg --pid ${PROFILE_PID} -r ${PROFILE_RATE} -d ${PROFILE_SECONDS} && curl -X POST http://storage.googleapis.com/${PROFILE_BUCKET} -F "key=${PROFILE_FILENAME}" -F "file=@profile.svg"
echo "Profiler output:"
echo https://storage.cloud.google.com/${PROFILE_BUCKET}/${PROFILE_FILENAME}