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
import os
import sys

import flask
from oslo_config import cfg
from oslo_log import log as logging
import six

from stackalytics.dashboard import memory_storage
from stackalytics.processor import runtime_storage
from stackalytics.processor import user_processor
from stackalytics.processor import utils


LOG = logging.getLogger(__name__)


RECORD_FIELDS_FOR_AGGREGATE = ['record_id', 'primary_key', 'record_type',
                               'company_name', 'module', 'user_id', 'release',
                               'date', 'week', 'author_name', 'loc', 'type',
                               'disagreement', 'value', 'status',
                               'blueprint_id']

CompactRecord = collections.namedtuple('CompactRecord',
                                       RECORD_FIELDS_FOR_AGGREGATE)


if six.PY2:
    _unihash = {}

    def uniintern(o):
        if not isinstance(o, basestring):
            return o
        if isinstance(o, str):
            return intern(o)
        if isinstance(o, unicode):
            return _unihash.setdefault(o, o)
else:
    def uniintern(o):
        if isinstance(o, str):
            return sys.intern(o)
        else:
            return o


def compact_records(records):
    for record in records:
        compact = dict((k, uniintern(record.get(k)))
                       for k in RECORD_FIELDS_FOR_AGGREGATE)

        yield CompactRecord(**compact)


def extend_record(record):
    runtime_storage_inst = get_runtime_storage()
    return runtime_storage_inst.get_by_key(
        runtime_storage_inst._get_record_name(record.record_id))


def get_vault():
    vault = getattr(flask.current_app, 'stackalytics_vault', None)
    if not vault:
        try:
            vault = {}
            runtime_storage_inst = runtime_storage.get_runtime_storage(
                cfg.CONF.runtime_storage_uri)
            vault['runtime_storage'] = runtime_storage_inst
            vault['memory_storage'] = memory_storage.get_memory_storage(
                memory_storage.MEMORY_STORAGE_CACHED)

            flask.current_app.stackalytics_vault = vault
        except Exception as e:
            LOG.critical('Failed to initialize application: %s', e)
            LOG.exception(e)
            flask.abort(500)

    if not getattr(flask.request, 'stackalytics_updated', None):
        time_now = utils.date_to_timestamp('now')
        may_update_by_time = time_now > vault.get('vault_next_update_time', 0)
        if may_update_by_time:
            flask.request.stackalytics_updated = True
            vault['vault_update_time'] = time_now
            vault['vault_next_update_time'] = (
                time_now + cfg.CONF.dashboard_update_interval)
            memory_storage_inst = vault['memory_storage']
            have_updates = memory_storage_inst.update(compact_records(
                vault['runtime_storage'].get_update(os.getpid())))
            vault['runtime_storage_update_time'] = (
                vault['runtime_storage'].get_by_key(
                    'runtime_storage_update_time'))

            if have_updates:
                vault['cache'] = {}
                vault['cache_size'] = 0
                _init_releases(vault)
                _init_module_groups(vault)
                _init_project_types(vault)
                _init_repos(vault)
                _init_user_index(vault)

    return vault


def get_memory_storage():
    return get_vault()['memory_storage']


def get_runtime_storage():
    return get_vault()['runtime_storage']


def _init_releases(vault):
    runtime_storage_inst = vault['runtime_storage']
    releases = runtime_storage_inst.get_by_key('releases')
    releases_map = {}

    if releases:
        vault['start_date'] = releases[0]['end_date']
        vault['end_date'] = releases[-1]['end_date']
        start_date = releases[0]['end_date']
        for r in releases[1:]:
            r['start_date'] = start_date
            start_date = r['end_date']
        releases_map = dict((r['release_name'].lower(), r)
                            for r in releases[1:])

    vault['releases'] = releases_map


def _init_module_groups(vault):
    runtime_storage_inst = vault['runtime_storage']
    module_groups = runtime_storage_inst.get_by_key('module_groups') or {}

    vault['module_id_index'] = module_groups


def _init_project_types(vault):
    runtime_storage_inst = vault['runtime_storage']
    project_types = runtime_storage_inst.get_by_key('project_types') or {}

    # add ref from child to parent
    parent_pt = None
    for pt in project_types:
        if pt.get('child'):
            pt['parent'] = parent_pt
        else:
            parent_pt = pt

    vault['project_types'] = project_types
    vault['project_types_index'] = dict((pt['id'], pt) for pt in project_types)


def _init_repos(vault):
    runtime_storage_inst = vault['runtime_storage']
    repos = runtime_storage_inst.get_by_key('repos') or {}

    vault['repos_index'] = dict((r['module'], r) for r in repos)


def _init_user_index(vault):
    vault['user_index'] = {}


def get_project_types():
    return get_vault()['project_types']


def get_release_options():
    runtime_storage_inst = get_runtime_storage()
    releases = (runtime_storage_inst.get_by_key('releases') or [None])[1:]
    releases.append({'release_name': 'all'})
    releases.reverse()
    return releases


def is_project_type_valid(project_type):
    if not project_type:
        return False
    project_type = project_type.lower()
    if project_type == 'all':
        return True
    project_types = get_vault().get('project_types_index', [])
    return project_type in project_types


def get_project_type(project_type_id):
    project_type_id = project_type_id.lower()
    if not is_project_type_valid(project_type_id):
        return None
    return get_vault()['project_types_index'][project_type_id]


def get_user_from_runtime_storage(user_id):
    runtime_storage_inst = get_runtime_storage()
    user_index = get_vault()['user_index']
    if user_id not in user_index:
        user_index[user_id] = user_processor.load_user(
            runtime_storage_inst, user_id=user_id)
    return user_index[user_id]


def _resolve_modules_for_releases(module_ids, releases):
    module_id_index = get_vault().get('module_id_index') or {}

    for module_id in module_ids:
        if module_id in module_id_index:
            module_group = module_id_index[module_id]

            if not releases or 'all' in releases:
                if 'releases' in module_group:
                    for release, modules in six.iteritems(
                            module_group['releases']):
                        for module in modules:
                            yield module, release
                if 'modules' in module_group:
                    for module in module_group['modules']:
                        yield module, None
            else:
                for release in releases:
                    if 'releases' in module_group:
                        for module in module_group['releases'][release]:
                            yield module, release
                    if 'modules' in module_group:
                        for module in module_group['modules']:
                            yield module, release


def resolve_modules(module_ids, releases):
    all_releases = get_vault()['releases'].keys()
    for module, release in _resolve_modules_for_releases(module_ids, releases):
        if release is None:
            for r in all_releases:
                yield (module, r)
        else:
            yield (module, release)


def resolve_project_types(project_types):
    modules = set()
    project_types_index = get_vault()['project_types_index']
    for pt in project_types:
        pt = pt.lower()
        if pt in project_types_index:
            modules |= set(project_types_index[pt]['modules'])
    return modules
