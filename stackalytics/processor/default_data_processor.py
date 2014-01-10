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

import hashlib
import json

from github import MainClass
import six

from stackalytics.openstack.common import log as logging
from stackalytics.processor import normalizer
from stackalytics.processor import record_processor
from stackalytics.processor import utils
from stackalytics.processor import vcs

LOG = logging.getLogger(__name__)


def _check_default_data_change(runtime_storage_inst, default_data):
    h = hashlib.new('sha1')
    h.update(json.dumps(default_data))
    digest = h.hexdigest()

    p_digest = runtime_storage_inst.get_by_key('default_data_digest')
    if digest == p_digest:
        LOG.debug('No changes in default data, sha1: %s', digest)
        return False

    LOG.debug('Default data has changes, sha1: %s', digest)
    runtime_storage_inst.set_by_key('default_data_digest', digest)
    return True


def _retrieve_project_list_from_github(project_sources):
    LOG.info('Retrieving project list from GitHub')
    github = MainClass.Github(timeout=60)

    repos = []
    for project_source in project_sources:
        organization = project_source['organization']
        LOG.debug('Get list of projects for organization %s', organization)
        try:
            github_repos = github.get_organization(organization).get_repos()
        except Exception as e:
            LOG.exception(e)
            LOG.warn('Fail to retrieve list of projects. Keep it unmodified')
            return False

        exclude = set(project_source.get('exclude', []))

        for repo in github_repos:
            if repo.name not in exclude:
                r = {
                    'branches': ['master'],
                    'module': repo.name,
                    'organization': organization,
                    'project_type': project_source['project_type'],
                    'project_group': project_source['project_group'],
                    'uri': repo.git_url,
                    'releases': []
                }
                repos.append(r)
                LOG.debug('Project is added to default data: %s', r)
    return repos


def _update_project_list(default_data):

    configured_repos = set([r['uri'] for r in default_data['repos']])

    repos = _retrieve_project_list_from_github(default_data['project_sources'])
    if repos:
        default_data['repos'] += [r for r in repos
                                  if r['uri'] not in configured_repos]


def _store_users(runtime_storage_inst, users):
    for user in users:
        stored_user = utils.load_user(runtime_storage_inst, user['user_id'])
        if stored_user:
            stored_user.update(user)
            user = stored_user
        utils.store_user(runtime_storage_inst, user)


def _store_companies(runtime_storage_inst, companies):
    domains_index = {}
    for company in companies:
        for domain in company['domains']:
            domains_index[domain] = company['company_name']
    runtime_storage_inst.set_by_key('companies', domains_index)


STORE_FUNCS = {
    'users': _store_users,
    'companies': _store_companies,
}


def _store_default_data(runtime_storage_inst, default_data):
    normalizer.normalize_default_data(default_data)

    LOG.debug('Update runtime storage with default data')
    for key, value in six.iteritems(default_data):
        if key in STORE_FUNCS:
            STORE_FUNCS[key](runtime_storage_inst, value)
        else:
            runtime_storage_inst.set_by_key(key, value)


def _update_records(runtime_storage_inst, sources_root):
    LOG.debug('Update existing records')
    release_index = {}
    for repo in utils.load_repos(runtime_storage_inst):
        vcs_inst = vcs.get_vcs(repo, sources_root)
        release_index.update(vcs_inst.get_release_index())

    record_processor_inst = record_processor.RecordProcessor(
        runtime_storage_inst)
    record_processor_inst.update(release_index)


def process(runtime_storage_inst, default_data, sources_root, force_update):
    LOG.debug('Process default data')

    dd_changed = _check_default_data_change(runtime_storage_inst, default_data)

    if 'project_sources' in default_data:
        _update_project_list(default_data)

    if dd_changed or force_update:
        _store_default_data(runtime_storage_inst, default_data)
        _update_records(runtime_storage_inst, sources_root)
