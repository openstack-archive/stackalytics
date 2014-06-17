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

import collections
import hashlib
import json

import six

from stackalytics.openstack.common import log as logging
from stackalytics.processor import normalizer
from stackalytics.processor import utils

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


def _retrieve_project_list_from_gerrit(project_sources, git_base_uri, gerrit):
    LOG.info('Retrieving project list from Gerrit')
    try:
        project_list = gerrit.get_project_list()
    except Exception as e:
        LOG.exception(e)
        LOG.warn('Fail to retrieve list of projects. Keep it unmodified')
        return False

    repos = []
    for project_source in project_sources:
        organization = project_source['organization']
        LOG.debug('Get list of projects for organization %s', organization)
        git_repos = [
            f for f in project_list if f.startswith(organization + "/")]

        exclude = set(project_source.get('exclude', []))

        for repo in git_repos:
            (org, name) = repo.split('/')
            if name not in exclude:
                url = '%(git_base_uri)s/%(repo)s.git' % dict(
                    git_base_uri=git_base_uri, repo=repo)
                r = {
                    'branches': ['master'],
                    'module': name,
                    'organization': org,
                    'uri': url,
                    'releases': []
                }
                repos.append(r)
                LOG.debug('Project is added to default data: %s', r)
    return repos


def _create_module_groups_for_project_sources(project_sources, repos):
    organizations = collections.defaultdict(list)
    for repo in repos:
        organizations[repo['organization']].append(repo['module'])

    ps_organizations = dict([(ps.get('organization'),
                              ps.get('module_group_name') or
                              ps.get('organization'))
                             for ps in project_sources])

    module_groups = []
    for ogn, modules in six.iteritems(organizations):
        module_groups.append(utils.make_module_group(
            ogn, name=ps_organizations.get(ogn, ogn), modules=modules,
            tag='organization'))

    return module_groups


def _update_project_list(default_data, git_base_uri, gerrit):

    configured_repos = set([r['uri'] for r in default_data['repos']])

    repos = _retrieve_project_list_from_gerrit(
        default_data['project_sources'], git_base_uri, gerrit)
    if repos:
        default_data['repos'] += [r for r in repos
                                  if r['uri'] not in configured_repos]

    default_data['module_groups'] += _create_module_groups_for_project_sources(
        default_data['project_sources'], default_data['repos'])


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

        if 'aliases' in company:
            for alias in company['aliases']:
                normalized_alias = utils.normalize_company_name(alias)
                domains_index[normalized_alias] = company['company_name']
        normalized_company_name = utils.normalize_company_name(
            company['company_name'])
        domains_index[normalized_company_name] = company['company_name']

    runtime_storage_inst.set_by_key('companies', domains_index)


def _store_module_groups(runtime_storage_inst, module_groups):
    stored_mg = runtime_storage_inst.get_by_key('module_groups') or {}
    for mg in module_groups:
        name = mg['module_group_name']
        module_group_id = mg.get('id') or name
        stored_mg[module_group_id] = utils.make_module_group(
            module_group_id, name=name, modules=mg['modules'],
            tag=mg.get('tag', 'group'))
    runtime_storage_inst.set_by_key('module_groups', stored_mg)


STORE_FUNCS = {
    'users': _store_users,
    'companies': _store_companies,
    'module_groups': _store_module_groups,
}


def _store_default_data(runtime_storage_inst, default_data):
    normalizer.normalize_default_data(default_data)

    LOG.debug('Update runtime storage with default data')
    for key, value in six.iteritems(default_data):
        if key in STORE_FUNCS:
            STORE_FUNCS[key](runtime_storage_inst, value)
        else:
            runtime_storage_inst.set_by_key(key, value)


def process(runtime_storage_inst, default_data,
            git_base_uri, gerrit):
    LOG.debug('Process default data')

    if 'project_sources' in default_data:
        _update_project_list(default_data, git_base_uri, gerrit)

    _store_default_data(runtime_storage_inst, default_data)
