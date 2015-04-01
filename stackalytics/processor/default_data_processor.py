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
import re

from github import MainClass
from oslo_config import cfg
from oslo_log import log as logging
import six

from stackalytics.processor import normalizer
from stackalytics.processor import rcs
from stackalytics.processor import user_processor
from stackalytics.processor import utils

LOG = logging.getLogger(__name__)

GITHUB_URI_PREFIX = r'^github:\/\/'


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


def _retrieve_project_list_from_sources(project_sources):
    for project_source in project_sources:
        uri = project_source.get('uri') or cfg.CONF.review_uri
        repo_iterator = []
        if re.search(rcs.GERRIT_URI_PREFIX, uri):
            repo_iterator = _retrieve_project_list_from_gerrit(project_source)
        elif re.search(GITHUB_URI_PREFIX, uri):
            repo_iterator = _retrieve_project_list_from_github(project_source)

        exclude = set(project_source.get('exclude', []))
        for repo in repo_iterator:
            if repo['module'] not in exclude:
                yield repo


def _retrieve_project_list_from_gerrit(project_source):
    LOG.info('Retrieving project list from Gerrit')
    try:
        uri = project_source.get('uri') or cfg.CONF.review_uri
        gerrit_inst = rcs.Gerrit(uri)
        key_filename = (project_source.get('ssh_key_filename') or
                        cfg.CONF.ssh_key_filename)
        username = project_source.get('ssh_username') or cfg.CONF.ssh_username
        gerrit_inst.setup(key_filename=key_filename, username=username)

        project_list = gerrit_inst.get_project_list()
        gerrit_inst.close()
    except Exception as e:
        LOG.exception(e)
        LOG.warn('Fail to retrieve list of projects. Keep it unmodified')
        return

    organization = project_source['organization']
    LOG.debug('Get list of projects for organization %s', organization)
    git_repos = [f for f in project_list if f.startswith(organization + "/")]

    git_base_uri = project_source.get('git_base_uri') or cfg.CONF.git_base_uri

    for repo in git_repos:
        (org, name) = repo.split('/')
        repo_uri = '%(git_base_uri)s/%(repo)s.git' % dict(
            git_base_uri=git_base_uri, repo=repo)
        yield {
            'branches': ['master'],
            'module': name,
            'organization': org,
            'uri': repo_uri,
            'releases': []
        }


def _retrieve_project_list_from_github(project_source):
    LOG.info('Retrieving project list from GitHub')
    github = MainClass.Github(timeout=60)

    organization = project_source['organization']
    LOG.debug('Get list of projects for organization %s', organization)
    try:
        github_repos = github.get_organization(organization).get_repos()
    except Exception as e:
        LOG.exception(e)
        LOG.warn('Fail to retrieve list of projects. Keep it unmodified')
        return

    for repo in github_repos:
        yield {
            'branches': [project_source.get('default_branch', 'master')],
            'module': repo.name.lower(),
            'organization': organization,
            'uri': repo.git_url,
            'releases': []
        }


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


def _update_project_list(default_data):

    configured_repos = set([r['uri'] for r in default_data['repos']])

    repos = _retrieve_project_list_from_sources(
        default_data['project_sources'])
    if repos:
        default_data['repos'] += [r for r in repos
                                  if r['uri'] not in configured_repos]

    default_data['module_groups'] += _create_module_groups_for_project_sources(
        default_data['project_sources'], default_data['repos'])


def _update_with_driverlog_data(default_data, driverlog_data_uri):
    LOG.info('Reading DriverLog data from uri: %s', driverlog_data_uri)
    driverlog_data = utils.read_json_from_uri(driverlog_data_uri)

    module_ci_ids = {}
    ci_ids = set()
    for driver in driverlog_data['drivers']:
        if 'ci' in driver:
            module = driver['project_id'].split('/')[1]

            if module not in module_ci_ids:
                module_ci_ids[module] = {}
            ci_id = driver['ci']['id']
            module_ci_ids[module][ci_id] = driver

            if ci_id not in ci_ids:
                ci_ids.add(ci_id)
                default_data['users'].append({
                    'user_id': user_processor.make_user_id(gerrit_id=ci_id),
                    'gerrit_id': ci_id,
                    'user_name': ci_id,
                    'static': True,
                    'companies': [
                        {'company_name': driver['vendor'], 'end_date': None}],
                })

    for repo in default_data['repos']:
        if repo['module'] in module_ci_ids:
            repo['ci'] = module_ci_ids[repo['module']]


def _store_users(runtime_storage_inst, users):
    for user in users:
        stored_user = user_processor.load_user(runtime_storage_inst,
                                               user_id=user['user_id'])
        if stored_user:
            stored_user.update(user)
            user = stored_user
        user['static'] = True
        user_processor.store_user(runtime_storage_inst, user)


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


def process(runtime_storage_inst, default_data, driverlog_data_uri):
    LOG.debug('Process default data')

    if 'project_sources' in default_data:
        _update_project_list(default_data)

    _update_with_driverlog_data(default_data, driverlog_data_uri)

    _store_default_data(runtime_storage_inst, default_data)
