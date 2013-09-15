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

import httplib
import urlparse

from stackalytics.openstack.common import log as logging
from stackalytics.processor import utils


LOG = logging.getLogger(__name__)

LINK_FIELDS = ['owner', 'drafter', 'starter', 'completer',
               'assignee', 'approver']
DATE_FIELDS = ['date_created', 'date_completed', 'date_started']


def _module_exists(module):
    uri = 'https://api.launchpad.net/devel/%s' % module
    parsed_uri = urlparse.urlparse(uri)
    conn = httplib.HTTPConnection(parsed_uri.netloc)
    conn.request('GET', parsed_uri.path)
    res = conn.getresponse()
    LOG.debug('Checked uri: %(uri)s, status: %(status)s',
              {'uri': uri, 'status': res.status})
    conn.close()
    return res.status != 404


def _link_to_launchpad_id(link):
    return link[link.find('~') + 1:]


def log(repo):
    module = repo['module']
    LOG.debug('Retrieving list of blueprints for module: %s', module)

    if not _module_exists(module):
        LOG.debug('Module %s not exist at Launchpad', module)
        return

    uri = 'https://api.launchpad.net/devel/%s/all_specifications' % module
    while True:
        LOG.debug('Reading chunk from uri %s', uri)
        chunk = utils.read_json_from_uri(uri)
        if 'next_collection_link' not in chunk:
            break
        uri = chunk['next_collection_link']

        for record in chunk['entries']:
            for field in LINK_FIELDS:
                link = record[field + '_link']
                if link:
                    record[field] = _link_to_launchpad_id(link)
                    del record[field + '_link']
            for field in DATE_FIELDS:
                date = record[field]
                if date:
                    record[field] = utils.iso8601_to_timestamp(date)

            record['module'] = module

            LOG.debug('New blueprint: %s', record)
            yield record
