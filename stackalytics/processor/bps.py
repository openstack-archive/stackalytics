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
DATE_FIELDS = ['date_created', 'date_fix_committed', 'date_fix_released']


def _get_bug_id(web_link):
    return web_link[web_link.rfind('/') + 1:]


def _log_module(module, primary_module, modified_since):
    for record_draft in launchpad_utils.lp_bug_generator(module,
                                                         modified_since):

        # record_draft can be a bug or bug target and
        # in the latter case it can be from a different module
        bug_target = record_draft['bug_target_name'].split('/')
        target_module = bug_target[0]
        if target_module != module:
            continue  # ignore foreigners

        record = {}

        if len(bug_target) == 2:
            record['release'] = bug_target[1]  # treat target as release

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
        record['module'] = primary_module
        record['id'] = utils.make_bug_id(bug_id, primary_module,
                                         record.get('release'))

        LOG.debug('New bug: %s', record)
        yield record


def log(repo, modified_since):
    repo_module = repo['module']
    modules = [repo_module] + repo.get('aliases', [])

    for module in modules:
        if not launchpad_utils.lp_module_exists(module):
            LOG.debug('Module %s does not exist at Launchpad, skip it', module)
            continue

        LOG.debug('Retrieving list of bugs for module: %s', module)

        for record in _log_module(module, repo_module, modified_since):
            yield record
