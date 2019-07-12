import requests
import click
import logging
from requests.auth import HTTPBasicAuth
from snsync.exceptions import UnknownAuthMethod

logger = logging.getLogger(__name__)


class SNClient(object):
    """ Very simple Service now client """

    def __init__(self, host, username=None, password=None,
                 headers=None, verify=True, read_only=False):
        self.host = host

        self._session = requests.Session()
        self._session.verify = verify

        # Setup for basic auth
        if username is not None and password is not None:
            self._session.auth = HTTPBasicAuth(username, password)

        self._session.headers = {
            "Content-Type": "application/json",
            "Accept": "application/json"
        }

        # Add any additional headers
        if headers:
            self._session.headers.update(headers)

    def format_query(self, query_dict):

        query = []

        for key, value in query_dict.items():
            query.append('{}={}'.format(key, value))

        query = '^'.join(query)

        return query

    def get(self, table, query=None, display=True, limit=None):
        """ Fetch a record from service now """

        params = {
            'displayvalue': display
        }

        if query:
            params['sysparm_query'] = self.format_query(query)

        if limit:
            params['sysparm_limit'] = limit

        resp = self._session.get("{host}/{table}.do?JSONv2".format(
            host=self.host, table=table), params=params)

        logger.debug("Requested: {}".format(resp.url))

        resp.raise_for_status()

        return resp.json()

    def create(self, table, values):
        pass

    def update(self, table, sys_id, values):
        """ Updates a record within Service Now
        :param table: Name of the table within Service Now
        :param sys_id: sys_id of the record
        :param values: dict containing the fields to update
        """

        params = {
            'displayvalue': True,
            'sysparm_query': 'sys_id={}'.format(sys_id),
            'sysparm_action': 'update'
        }

        resp = self._session.post(
            "{host}/{table}.do?JSONv2".format(host=self.host, table=table),
            params=params,
            json=values
        )

        logger.debug("Requested: {}".format(resp.url))

        resp.raise_for_status()
        return resp.json()
