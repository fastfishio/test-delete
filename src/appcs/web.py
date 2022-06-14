import json
import logging
import time
import random

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.requests import Request
from noonutil.v1 import fastapiutil, logsql
from pydantic import ValidationError as ResponseValidationError
from sentry_sdk.integrations.asgi import SentryAsgiMiddleware
from sqlalchemy.exc import DatabaseError

from libcs import DomainException
from liborder import Context
from libutil import util
from libaccess.models import util as libaccess_util

logger = logging.getLogger(__name__)

METRICS_PERCENTAGE = 80

app_params = {
    "title": "mp-boilerplate CS API",
    "description": "Public CS API for boilerplate",
    "version": "0.1.0",
    "docs_url": '/swagger',
    "redoc_url": '/docs',
}

app = FastAPI(**app_params)
mk = 'appcs'
app.debug = not Context.is_production
g = fastapiutil.get_request_state_proxy(app)

errhandler_400 = util.generate_exception_handler(400, monitoring_key=mk)
errhandler_400tb = util.generate_exception_handler(400, include_traceback=True, monitoring_key=mk)
errhandler_404 = fastapiutil.generate_exception_handler(404)

app.add_exception_handler(RequestValidationError, errhandler_400)
app.add_exception_handler(AssertionError, errhandler_400tb)
app.add_exception_handler(DomainException, errhandler_400tb)

if Context.is_production:
    errhandler_500 = util.generate_exception_handler(
        500, sentry_level='error', client_error_message="Sorry, something wrong on our side", monitoring_key=mk
    )
    app.add_exception_handler(ResponseValidationError, errhandler_500)
    app.add_exception_handler(DatabaseError, errhandler_500)
    app.add_exception_handler(Exception, errhandler_500)


@app.middleware('http')
async def before_request(request: Request, call_next):
    api_start_time = time.perf_counter_ns()
    if request.url.path != '/public/hc':
        request.state.user_code = libaccess_util.sanitize_code(request.headers['x-forwarded-user'])
        request.state.lat = None
        request.state.lng = None
        request.state.visitor_id = None
        request.state.customer_code = None
        locale = request.headers.get("x-locale") or "en-ae"
        lang, country_code = locale.split("-")
        lang = lang.lower() if lang.lower() in ('ar', 'en') else 'en'
        country_code = country_code.lower()
        request.state.host = request.headers.get('host')
        request.state.visitor_id = request.headers.get('x-visitor-id') or ''
        request.state.customer_code = request.headers.get('x-forwarded-for') or ''
        request.state.lang = lang
        request.state.country_code = country_code
        # hack to unblock nipun
        request.state.address_key = ''
    res = await call_next(request)
    api_end_time = time.perf_counter_ns()
    if request.url.path != '/public/hc':
        rnd = random.random()
        if rnd <= METRICS_PERCENTAGE:
            logger.info(
                "perf-metrics",
                extra={
                    'method': request.method,
                    'path': request.url.path,
                    'code': res.status_code,
                    'time_ms': (api_end_time - api_start_time) / 1000000,
                },
            )
    return res


@app.get("/public/hc", status_code=200, tags=['system'])
def health_check():
    return "OK"


logsql.init()

from appcs.views import router

app.include_router(router)
app = SentryAsgiMiddleware(app)
