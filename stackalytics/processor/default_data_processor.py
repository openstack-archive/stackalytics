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

from stackalytics.openstack.common import log as logging
from stackalytics.processor import normalizer
from stackalytics.processor import record_processor
from stackalytics.processor import vcs

LOG = logging.getLogger(__name__)


def _check_default_data_change(runtime_storage_inst, default_data):
    h = hashlib.new('sha1')
    h.update(json.dumps(default_data))
    digest = h.hexdigest()

    p_digest = runtime_storage_inst.get_by_key('default_data_digest')
    if digest == p_digest:
        LOG.debug('No changes in default data detected, sha1: %s', digest)
        return False

    LOG.debug('Default data has changes, sha1: %s', digest)
    runtime_storage_inst.set_by_key('default_data_digest', digest)
    return True


def _retrieve_project_list(runtime_storage_inst, project_sources):

    LOG.info('Retrieving project list from GitHub')

    repo_index = {}
    stored_repos = runtime_storage_inst.get_by_key('repos')
    for repo in stored_repos:
        repo_index[repo['uri']] = repo

    github = MainClass.Github()

    for project_source in project_sources:
        organization = project_source['organization']
        repos = github.get_organization(organization).get_repos()
        LOG.debug('Get list of projects for organization %s', organization)

        for repo in repos:
            repo_uri = repo.git_url
            repo_name = repo.name

            if repo_uri not in repo_index:
                r = {
                    'branches': ['master'],
                    'module': repo_name,
                    'project_type': project_source['project_type'],
                    'project_group': project_source['project_group'],
                    'uri': repo_uri,
                    'releases': []
                }
                stored_repos.append(r)
                LOG.debug('Project is added to default data: %s', r)

    runtime_storage_inst.set_by_key('repos', stored_repos)


def _process_users(users):
    users_index = {}
    for user in users:
        if 'user_id' in user:
            users_index[user['user_id']] = user
        if 'launchpad_id' in user:
            users_index[user['launchpad_id']] = user
        for email in user['emails']:
            users_index[email] = user
    return users_index


def _process_companies(companies):
    domains_index = {}
    for company in companies:
        for domain in company['domains']:
            domains_index[domain] = company['company_name']
    return domains_index


KEYS = {
    'users': _process_users,
    'repos': None,
    'releases': None,
    'companies': _process_companies,
}


def _update_default_data(runtime_storage_inst, default_data):
    for key, processor in KEYS.iteritems():
        if processor:
            value = processor(default_data[key])
        else:
            value = default_data[key]
        runtime_storage_inst.set_by_key(key, value)


def process(runtime_storage_inst, default_data, sources_root):

    normalizer.normalize_default_data(default_data)

    if _check_default_data_change(runtime_storage_inst, default_data):

        _update_default_data(runtime_storage_inst, default_data)

        release_index = {}
        for repo in runtime_storage_inst.get_by_key('repos'):
            vcs_inst = vcs.get_vcs(repo, sources_root)
            release_index.update(vcs_inst.get_release_index())

        record_processor_inst = record_processor.RecordProcessor(
            runtime_storage_inst)
        updated_records = record_processor_inst.update(
            runtime_storage_inst.get_all_records(), release_index)
        runtime_storage_inst.set_records(updated_records)

    if 'project_sources' in default_data:
        _retrieve_project_list(runtime_storage_inst,
                               default_data['project_sources'])
