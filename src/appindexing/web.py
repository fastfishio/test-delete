import logging

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError, HTTPException
from fastapi.requests import Request
from noonutil.v1 import fastapiutil, logsql
from pydantic import ValidationError as ResponseValidationError
from sentry_sdk.integrations.asgi import SentryAsgiMiddleware
from sqlalchemy.exc import DatabaseError, IntegrityError, OperationalError
from libutil import util
from libcatalog import DomainException, Context
from libcatalog import NotFoundException


logger = logging.getLogger(__name__)

app_params = {
    "title": "mp-boilerplate Indexing API",
    "description": "Indexing is currently does not serve any endpoint",
    "version": "0.1.0",
    "docs_url": None,
    "redoc_url": None,
}

app = FastAPI(**app_params)
mk = 'appmpnoon'
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


@app.middleware('http')
def before_request(request: Request, call_next):
    return call_next(request)


@app.get("/public/hc", status_code=200, tags=['system'])
def health_check():
    return "OK"


logsql.init()

app = SentryAsgiMiddleware(app)
