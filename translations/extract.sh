#!/bin/sh
cd "${0%/*}"

cd ../ && pybabel extract --sort-by-file --omit-header -F translations/babel.cfg -k lazy_gettext -o translations/en.pot .

