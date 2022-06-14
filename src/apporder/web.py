import logging
import time
import random
import os

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.requests import Request
from noonutil.v1 import fastapiutil
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.requests import RequestsInstrumentor
from pydantic import ValidationError as ResponseValidationError
from sentry_sdk.integrations.asgi import SentryAsgiMiddleware
from sqlalchemy.exc import DatabaseError

from libcatalog import DomainException
from liborder import Context
from libutil import tracer
from libutil import translation
from libutil import util

METRICS_PERCENTAGE = 0.8

logger = logging.getLogger(__name__)

app_params = {
    "title": "mp-boilerplate Order API",
    "description": "Public Order API for mp-boilerplate",
    "version": "0.1.0",
    "docs_url": '/swagger',
    "redoc_url": '/docs',
}

app = FastAPI(**app_params)
mk = 'apporder'
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

FastAPIInstrumentor.instrument_app(app, tracer_provider=tracer.tracer_provider, excluded_urls='/public/hc')
RequestsInstrumentor().instrument(tracer_provider=tracer.tracer_provider)


@app.middleware('http')
async def before_request(request: Request, call_next):
    api_start_time = time.perf_counter_ns()
    if request.url.path != '/public/hc':
        request.state.user_code = None
        request.state.customer_code = request.headers.get('x-forwarded-user')
        request.state.visitor_id = request.headers.get('X-Visitor-Id')
        request.state.lat = request.headers.get('X-Lat')
        request.state.lng = request.headers.get('X-Lng')
        request.state.address_key = request.headers.get('x-addresskey')
        if os.getenv('ENV') in ('dev', 'staging'):
            if not request.state.visitor_id:
                request.state.visitor_id = 'v1'
            if not request.state.lat:
                request.state.lat = 251952139
            if not request.state.lng:
                request.state.lng = 552779116
        locale = (request.headers.get('x-locale') or 'en-ae').lower()
        # todo: check this again
        language, country = locale.split('-')[:2] if '-' in locale else (locale, locale)
        request.state.country_code = country if country in ('ae', 'sa', 'eg') else 'ae'
        request.state.lang = language if language in ('en', 'ar') else 'en'
        translation.set_current_language(request.state.lang)
        request.state.host = request.headers.get('host')
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


if os.getenv('ENV') in ('dev', 'staging', 'prod'):
    fastapiutil.add_default_openapi_parameters(
        app,
        [
            {'name': 'X-Visitor-Id', 'type': 'string', 'in': 'header', 'description': 'Visitor ID'},
            {'name': 'X-Lat', 'type': 'int', 'in': 'header', 'description': 'Address Lat'},
            {'name': 'X-Lng', 'type': 'int', 'in': 'header', 'description': 'Address Lng'},
            {'name': 'X-addresskey', 'type': 'string', 'in': 'header', 'description': 'Address Key'},
            {'name': 'x-locale', 'type': 'string', 'in': 'header', 'description': 'Locale'},
        ],
    )

from apporder.urls import api_router

app.include_router(api_router)
app = SentryAsgiMiddleware(app)
