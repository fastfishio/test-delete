#!/bin/sh
set -x

if test "${ENV}" != 'dev'; then
  if test "${APPNAME}" = "mp-boilerplate-api-catalog" ; then
    gunicorn --log-level info -b 0.0.0.0:8080 --timeout=15 --worker-class=uvicorn.workers.UvicornWorker --workers 5 appcatalog.web:app
  elif test "${APPNAME}" = "mp-boilerplate-api-cs" ; then
    gunicorn --log-level info -b 0.0.0.0:8080 --timeout=15 --worker-class=uvicorn.workers.UvicornWorker --workers 5 appcs.web:app
  elif test "${APPNAME}" = "mp-boilerplate-api-team" ; then
    gunicorn --log-level info -b 0.0.0.0:8080 --timeout=15 --worker-class=uvicorn.workers.UvicornWorker --workers 5 appteam.web:app
  elif test "${APPNAME}" = "mp-boilerplate-api-indexing" ; then
    gunicorn --log-level info -b 0.0.0.0:8080 --timeout=15 --worker-class=uvicorn.workers.UvicornWorker --workers 5 appindexing.web:app
  else
    gunicorn --log-level info -b 0.0.0.0:8080 --timeout=15 --worker-class=uvicorn.workers.UvicornWorker --workers 5 apporder.web:app
  fi
else
  if test "${APPNAME}" = "mp-boilerplate-api-catalog" ; then
    uvicorn appcatalog.web:app --host 0.0.0.0 --port 8080 --reload --log-level debug 
  elif test "${APPNAME}" = "mp-boilerplate-api-cs" ; then
    uvicorn appcs.web:app --host 0.0.0.0 --port 8080 --reload --log-level debug 
  elif test "${APPNAME}" = "mp-boilerplate-api-team" ; then
    uvicorn appteam.web:app --host 0.0.0.0 --port 8080 --reload --log-level debug 
  elif test "${APPNAME}" = "mp-boilerplate-api-indexing" ; then
    uvicorn appindexing.web:app --host 0.0.0.0 --port 8080 --reload --log-level debug 
  else
    uvicorn apporder.web:app --host 0.0.0.0 --port 8080 --reload --log-level debug 
  fi
fi
