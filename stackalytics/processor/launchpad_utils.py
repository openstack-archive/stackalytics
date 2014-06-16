# Copyright (c) 2013 Mirantis Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import six
from six.moves import http_client
from six.moves.urllib import parse

from stackalytics.openstack.common import log as logging
from stackalytics.processor import utils


LOG = logging.getLogger(__name__)

BUG_STATUSES = ['New', 'Incomplete', 'Opinion', 'Invalid', 'Won\'t Fix',
                'Expired', 'Confirmed', 'Triaged', 'In Progress',
                'Fix Committed', 'Fix Released',
                'Incomplete (with response)',
                'Incomplete (without response)']
LP_URI_V1 = 'https://api.launchpad.net/1.0/%s'
LP_URI_DEVEL = 'https://api.launchpad.net/devel/%s'


def link_to_launchpad_id(link):
    return link[link.find('~') + 1:]


def lp_profile_by_launchpad_id(launchpad_id):
    LOG.debug('Lookup user id %s at Launchpad', launchpad_id)
    uri = LP_URI_V1 % ('~' + launchpad_id)
    return utils.read_json_from_uri(uri)


def lp_profile_by_email(email):
    LOG.debug('Lookup user email %s at Launchpad', email)
    uri = LP_URI_V1 % ('people/?ws.op=getByEmail&email=' + email)
    return utils.read_json_from_uri(uri)


def lp_module_exists(module):
    uri = LP_URI_DEVEL % module
    parsed_uri = parse.urlparse(uri)
    conn = http_client.HTTPConnection(parsed_uri.netloc)
    conn.request('GET', parsed_uri.path)
    res = conn.getresponse()
    LOG.debug('Checked uri: %(uri)s, status: %(status)s',
              {'uri': uri, 'status': res.status})
    conn.close()
    return res.status != 404


def lp_blueprint_generator(module):
    uri = LP_URI_DEVEL % (module + '/all_specifications')
    while uri:
        LOG.debug('Reading chunk from uri %s', uri)
        chunk = utils.read_json_from_uri(uri)

        if not chunk:
            LOG.warn('No data was read from uri %s', uri)
            break

        for record in chunk['entries']:
            yield record

        uri = chunk.get('next_collection_link')


def lp_bug_generator(module, modified_since):
    uri = LP_URI_DEVEL % (module + '?ws.op=searchTasks')
    for status in BUG_STATUSES:
        uri += '&status=' + six.moves.urllib.parse.quote_plus(status)
    if modified_since:
        uri += '&modified_since=' + utils.timestamp_to_utc_date(modified_since)

    while uri:
        LOG.debug('Reading chunk from uri %s', uri)
        chunk = utils.read_json_from_uri(uri)

        if not chunk:
            LOG.warn('No data was read from uri %s', uri)
            break

        for record in chunk['entries']:
            yield record

        uri = chunk.get('next_collection_link')
