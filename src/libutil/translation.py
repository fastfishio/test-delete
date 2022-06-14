from noonutil.v1 import miscutil
import gettext
from gettext import NullTranslations, translation
import os
from contextvars import ContextVar
import logging
from lazy_string import LazyString

logger = logging.getLogger(__name__)

CURRENT_LANGUAGE_CODE = ContextVar('current_language_code', default=None)


IS_TESTING = os.getenv('TESTING') == 'pytest'


@miscutil.cached()
def get_translations(lang):
    lang = (lang or 'en').lower()
    if lang == 'en':
        return NullTranslations()
    ret = translation('messages', localedir='/src/translations', languages=[lang])
    if not IS_TESTING:
        return ret
    testret = MockGettext()
    testret.add_fallback(ret)
    return testret


class DynamicGettext:
    def __init__(self, lang_fn):
        self.lang_fn = lang_fn

    def gettext(self, s):
        return get_translations(self.lang_fn()).gettext(s)


class MockGettext(NullTranslations):
    def gettext(self, s):
        if s == 'test string':
            return 'test string arabic'
        return super().gettext(s)

# language ctx

def get_current_language():
    return CURRENT_LANGUAGE_CODE.get() or 'en'

def set_current_language(lang):
    CURRENT_LANGUAGE_CODE.set(lang)

gettext = DynamicGettext(get_current_language)
_ = gettext.gettext

def lazy_gettext(s):
    return LazyString(gettext.gettext, s)

# add LazyString support to FastAPI JSON encoder
import fastapi.encoders
fastapi.encoders.ENCODERS_BY_TYPE[LazyString] = str


def combine(left_str, right_str, sep=' '):
    if get_current_language() == 'en':
        return f'{left_str}{sep}{right_str}'
    else:
        return f'{right_str}{sep}{left_str}'
