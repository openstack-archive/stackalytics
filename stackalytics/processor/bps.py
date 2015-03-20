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

from oslo_log import log as logging

from stackalytics.processor import launchpad_utils
from stackalytics.processor import utils


LOG = logging.getLogger(__name__)

LINK_FIELDS = ['owner', 'assignee']
BUG_FIELDS = ['web_link', 'status', 'title', 'importance']
DATE_FIELDS = ['date_created', 'date_fix_committed']


def _get_bug_id(web_link):
    return web_link[web_link.rfind('/') + 1:]


def log(repo, modified_since):
    module = repo['module']
    LOG.debug('Retrieving list of bugs for module: %s', module)

    if not launchpad_utils.lp_module_exists(module):
        LOG.debug('Module %s does not exist at Launchpad', module)
        return

    for record_draft in launchpad_utils.lp_bug_generator(module,
                                                         modified_since):

        record = {}

        for field in LINK_FIELDS:
            link = record_draft[field + '_link']
            if link:
                record[field] = launchpad_utils.link_to_launchpad_id(link)

        for field in BUG_FIELDS:
            record[field] = record_draft[field]

        for field in DATE_FIELDS:
            date = record_draft[field]
            if date:
                record[field] = utils.iso8601_to_timestamp(date)

        bug_id = _get_bug_id(record_draft['web_link'])
        record['module'] = module
        record['id'] = utils.get_bug_id(module, bug_id)

        LOG.debug('New bug: %s', record)
        yield record
