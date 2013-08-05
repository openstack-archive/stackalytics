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

    p_digest = runtime_storage_inst.get_last_id('default_data_digest')
    if digest == p_digest:
        LOG.debug('No changes in default data detected, sha1: %s', digest)
        return False

    LOG.debug('Default data has changes, sha1: %s', digest)
    runtime_storage_inst.set_last_id('default_data_digest', digest)
    return True


def _retrieve_project_list(default_data):

    if 'project_sources' not in default_data:
        return

    LOG.info('Retrieving project list from GitHub')

    repo_index = {}
    for repo in default_data['repos']:
        repo_index[repo['uri']] = repo

    github = MainClass.Github()

    for project_source in default_data['project_sources']:
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
                    'uri': repo_uri
                }
                default_data['repos'].append(r)
                LOG.debug('Project is added to default data: %s', r)


def process(persistent_storage_inst, runtime_storage_inst, default_data,
            sources_root):

    _retrieve_project_list(default_data)

    normalizer.normalize_default_data(default_data)

    if _check_default_data_change(runtime_storage_inst, default_data):

        persistent_storage_inst.reset(default_data)

        release_index = {}
        for repo in persistent_storage_inst.find('repos'):
            vcs_inst = vcs.get_vcs(repo, sources_root)
            release_index.update(vcs_inst.get_release_index())

        record_processor_inst = record_processor.RecordProcessor(
            persistent_storage_inst)
        updated_records = record_processor_inst.update(
            runtime_storage_inst.get_all_records(), release_index)
        runtime_storage_inst.set_records(updated_records)
