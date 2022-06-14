import logging
import os
import time
import random

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.requests import Request
from noonutil.v1 import fastapiutil, logsql
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.requests import RequestsInstrumentor
from pydantic import ValidationError as ResponseValidationError
from sentry_sdk.integrations.asgi import SentryAsgiMiddleware
from sqlalchemy.exc import DatabaseError

from libcatalog import DomainException, Context, NotFoundException
from libutil import tracer
from libutil import util
from libutil.query_parser import NestedQueryParams

logger = logging.getLogger(__name__)

METRICS_PERCENTAGE = 0.8

app_params = {
    "title": "mp-boilerplate Catalog API",
    "description": "Public Catalog API for mp-boilerplate",
    "version": "0.1.0",
    "docs_url": '/swagger',
    "redoc_url": '/docs',
}

app = FastAPI(**app_params)
mk = 'appcatalog'
app.debug = not Context.is_production
g = fastapiutil.get_request_state_proxy(app)

errhandler_400 = util.generate_exception_handler(400, monitoring_key=mk)
errhandler_400tb = util.generate_exception_handler(400, include_traceback=True, monitoring_key=mk)
errhandler_404 = fastapiutil.generate_exception_handler(404)

app.add_exception_handler(RequestValidationError, errhandler_400)
app.add_exception_handler(AssertionError, errhandler_400tb)
app.add_exception_handler(DomainException, errhandler_400tb)
app.add_exception_handler(NotFoundException, errhandler_404)

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
    # really bad hack, sorry - swagger was calling with /openapi.json
    #  and then it was failing because lat/lng was not passed
    if not any(x in request.url.path for x in ['/public/hc', '/swagger', '/openapi.json']):
        locale = request.headers.get("x-locale") or "en-ae"
        lang, country_code = locale.split("-")
        lang = lang.lower() if lang.lower() in ('ar', 'en') else 'en'
        country_code = country_code.lower()
        request.state.query_params = NestedQueryParams(str(request.query_params))
        request.state.host = request.headers.get('host')
        request.state.visitor_id = request.headers.get('x-visitor-id') or ''
        request.state.customer_code = request.headers.get('x-forwarded-for') or ''
        if request.query_params.get('productsOnly'):
            request.state.is_product_carousel = True
        else:
            request.state.is_product_carousel = False
        request.state.lang = lang
        request.state.country_code = country_code
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
                    'time_ms': (api_end_time - api_start_time) / 1000000
                }
            )
    return res


@app.get("/public/hc", status_code=200, tags=['system'])
def health_check():
    return "OK"


logsql.init()

from appcatalog.views import router

if os.getenv('ENV') in ('dev', 'staging', 'prod'):
    fastapiutil.add_default_openapi_parameters(app, [
        {'name': 'X-Lat', 'type': 'int', 'in': 'header', 'description': 'Address Lat'},
        {'name': 'X-Lng', 'type': 'int', 'in': 'header', 'description': 'Address Lng'}
    ])

app.include_router(router)
app = SentryAsgiMiddleware(app)
