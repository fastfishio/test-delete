import logging
import os

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.requests import Request
from noonutil.v1 import fastapiutil
from pydantic import ValidationError as ResponseValidationError
from sentry_sdk.integrations.asgi import SentryAsgiMiddleware
from sqlalchemy.exc import DatabaseError

from liborder import DomainException, Context
from libutil import util

logger = logging.getLogger(__name__)

app_params = {
    "title": "mp-boilerplate Team API",
    "description": "Internal API for mp-boilerplate",
    "version": "0.1.0",
    "docs_url": '/swagger',
    "redoc_url": '/docs',
}

app = FastAPI(**app_params)
app.debug = not Context.is_production
g = fastapiutil.get_request_state_proxy(app)
mk = 'appteam'
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
def before_request(request: Request, call_next):
    import json
    if request.url.path != '/public/hc':
        user = {}
        lang, country = None, None
        if 'N-User' in request.headers and not request.url.path.startswith('/public'):
            user = json.loads(request.headers.get('N-User'))
        elif os.getenv('ENV') == 'dev':
            user = {'email': 'svc@noon.team', 'roles': ['admin']}
        if Context.is_testing:
            lang = 'en'
        locale = request.headers.get('x-locale')
        if locale:
            lang, country = locale.split('-')
        request.state.lang = request.headers.get('N-Lang') or lang
        request.state.country_code = request.headers.get('N-CountryCode') or country
        request.state.host = request.headers.get('host')
        request.state.user_code = user.get('email')
        request.state.username = user.get('username')
        request.state.team_domain_roles = user.get('roles', [])
    return call_next(request)


@app.get("/public/hc", status_code=200, tags=['system'])
def health_check():
    return "OK"


from appteam.views import router

app.include_router(router)
app = SentryAsgiMiddleware(app)
