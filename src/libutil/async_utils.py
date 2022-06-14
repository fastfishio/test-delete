import copy
import functools
import time
import http3
import json
from collections import namedtuple
from typing import List, Any
from retrying_async import retry
from noonutil.v1 import miscutil
import copy

class TooManyTriesException(BaseException):
    pass


ENGINES = {}

MEMO = namedtuple('memo', ['data', 'time'])

def tries(times):
    def func_wrapper(f):
        async def wrapper(*args, **kwargs):
            for time in range(times):
                try:
                    return await f(*args, **kwargs)
                except Exception as exc:
                    pass
            raise TooManyTriesException() from exc
        return wrapper
    return func_wrapper



class cached:
    class _Key:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

        def __eq__(self, obj):
            return hash(self) == hash(obj)

        def __hash__(self):
            def _hash(param: Any):
                if isinstance(param, tuple):
                    return tuple(map(_hash, param))
                if isinstance(param, dict):
                    return tuple(map(_hash, param.items()))
                elif hasattr(param, '__dict__'):
                    return str(vars(param))
                else:
                    return str(param)
            return hash(_hash(self.args) + _hash(self.kwargs))

    def __init__(self, ttl=None, copy=False):
        self.ttl = ttl
        self.memo = {}
        self.copy = copy

    def __call__(self, func):
        async def wrapper(*args, **kwargs):
            key = self._Key(args, kwargs)
            if key in self.memo:
                da = self.memo[key]
                if self.ttl:
                    t = time.time() - da.time
                    if t < self.ttl:
                        if self.copy:
                            return copy.deepcopy(da.data)
                        return da.data
                else:
                    return da.data
            data = await func(*args, **kwargs)
            da = MEMO(data=data, time=time.time())
            self.memo[key] = da
            if self.copy:
                return copy.deepcopy(self.memo[key].data)
            return self.memo[key].data

        wrapper.__name__ += func.__name__
        return wrapper


@retry(attempts=3, delay=3)
async def async_get(url: str):

    client = http3.AsyncClient(timeout=180)
    response = await client.get(url)
    if response.status_code == 200:
        return response.json()
    return {"error": True, "response": response.text}

@retry(attempts=3, delay=3)
async def async_post(url: str, data: dict | List[dict], headers={}):

    client = http3.AsyncClient(timeout=180)
    data = json.dumps(data)
    headers = {'content-type': 'application/json'}
    response = await client.post(url, data=data, headers=headers)
    if response.status_code == 200:
        return response.json()
    return {"error": True, "response": response.text}



def groupby(data, uq=[], grp=[]):
    new_data = []
    key_func = lambda r: [r[k]for k in uq]
    return {key[0] if len(key) == 1 else tuple(key): value for key, value in miscutil.groupby(data, key_func)}

import concurrent.futures
SYNC_THREADPOOL = concurrent.futures.ThreadPoolExecutor(max_workers=10)
def asql(*args, **kwargs):
    from jsql import sql
    import asyncio
    loop = asyncio.get_running_loop()
    return loop.run_in_executor(SYNC_THREADPOOL, lambda: sql(*args, **kwargs))


def asyncify(new_threadpool_size:int=None):
    if new_threadpool_size is not None:
        threadpool = concurrent.futures.ThreadPoolExecutor(max_workers=new_threadpool_size)
    else:
        threadpool = SYNC_THREADPOOL

    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args,**kwargs):
            import asyncio
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(threadpool, lambda: func(*args, **kwargs))
        return wrapper
    return decorator