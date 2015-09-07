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

LINK_FIELDS = ['owner', 'drafter', 'starter', 'completer',
               'assignee', 'approver']
DATE_FIELDS = ['date_created', 'date_completed', 'date_started']


def _log_module(module, primary_module):
    for record in launchpad_utils.lp_blueprint_generator(module):
        for field in LINK_FIELDS:
            link = record[field + '_link']
            if link:
                record[field] = launchpad_utils.link_to_launchpad_id(link)
                del record[field + '_link']
        for field in DATE_FIELDS:
            date = record[field]
            if date:
                record[field] = utils.iso8601_to_timestamp(date)

        record['module'] = primary_module
        record['id'] = utils.get_blueprint_id(primary_module, record['name'])

        LOG.debug('New blueprint: %s', record)
        yield record


def log(repo):
    repo_module = repo['module']
    modules = [repo_module] + repo.get('aliases', [])

    for module in modules:
        if not launchpad_utils.lp_module_exists(module):
            LOG.debug('Module %s does not exist at Launchpad, skip it', module)
            return

        LOG.debug('Retrieving list of blueprints for module: %s', module)
        for record in _log_module(module, repo_module):
            yield record
