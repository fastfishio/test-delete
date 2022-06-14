import aiosolr
import requests

from libutil.spanner_util import *

SOLR_SEMAPHORE = os.getenv('SOLR_SEMAPHORE') or 2

logger = logging.getLogger(__name__)

SOLR_HOST = os.getenv('SOLR_HOST') or 'localhost'


class Solr(aiosolr.Solr):

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self.close()

    def _kwarg_to_query_string(self, kwargs):
        """
            overriding origional params
            Convert kwarg arguments to Solr query string.
        """
        query_string = "&"
        params = kwargs.pop("params", [])
        query_string += "&".join(params)
        for param, value in kwargs.items():
            if isinstance(value, list):
                separator = "+" if param in ("qf",) else ","
                query_string += "&{}={}".format(param, separator.join(value))
            else:
                query_string += f"&{param}={value}"
        return query_string

    async def query(
            self,
            handler="select",
            query="*",
            spellcheck=False,
            spellcheck_dicts=[],
            **kwargs,
    ):
        """Query a requestHandler of class SearchHandler."""
        collection = self._get_collection(kwargs)
        query = requests.utils.quote(query)
        url = f"{self.base_url}/{collection}/{handler}?q={query}&wt={self.response_writer}"
        if spellcheck:
            url += "&spellcheck=on"
            for spellcheck_dict in spellcheck_dicts:
                url += f"&spellcheck.dictionary={spellcheck_dict}"
        url += self._kwarg_to_query_string(kwargs)
        if IS_TESTING:
            logger.warning('SOLRURL: %s', url)
        response = await self._get(url)
        if response.status == 200:
            data = self._deserialize(response.body)
        else:
            raise aiosolr.SolrError("%s", response.body)
        return data

    async def delete(
            self,
            ids,
            attr: str = "object_id",
            **kwargs
    ):
        assert (not isinstance(ids, (list, tuple))), "solr delete not supported for list for now (still todo)"
        if isinstance(ids, (list, tuple)):
            ids = " OR ".join(ids)

        data = {"delete": {"id": ids}}
        await self.update(data, **kwargs)
        await self.commit()

    async def add(
            self,
            doc,
            **kwargs
    ):
        data = {"add": {"doc": doc}}
        await self.update(data, **kwargs)
        await self.commit()

    async def clear(self):
        data = {"delete": {"query": "*:*"}}
        return await self.update(data, commit="false")


class BoilerplateSolr(Solr):
    async def query(
            self,
            handler="select",
            query="*",
            spellcheck=False,
            spellcheck_dicts=[],
            **kwargs,
    ):
        if not kwargs['params']:
            kwargs['params'] = []
        return await super().query(handler=handler, query=query,
                                   spellcheck=spellcheck, spellcheck_dicts=spellcheck_dicts, **kwargs)
