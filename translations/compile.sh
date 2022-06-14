#!/bin/sh
cd /src/translations

mkdir -p ar/LC_MESSAGES/ && pybabel compile -f -i ar.po -d . -o ./ar/LC_MESSAGES/messages.mo

