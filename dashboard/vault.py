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

import flask
from oslo.config import cfg

from dashboard import memory_storage
from stackalytics.openstack.common import log as logging
from stackalytics.processor import runtime_storage
from stackalytics.processor import utils


LOG = logging.getLogger(__name__)


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

            init_releases(vault)

            flask.current_app.stackalytics_vault = vault
        except Exception as e:
            LOG.critical('Failed to initialize application: %s', e)
            LOG.exception(e)
            flask.abort(500)

    if not getattr(flask.request, 'stackalytics_updated', None):
        flask.request.stackalytics_updated = True
        memory_storage_inst = vault['memory_storage']
        have_updates = memory_storage_inst.update(
            vault['runtime_storage'].get_update(os.getpid()))

        if have_updates:
            init_releases(vault)
            init_module_groups(vault)
            init_project_types(vault)

    return vault


def get_memory_storage():
    return get_vault()['memory_storage']


def init_releases(vault):
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


def _make_module(module_id, text, modules, tag):
    return {'id': module_id, 'text': text,
            'modules': modules, 'tag': tag}


def init_module_groups(vault):
    runtime_storage_inst = vault['runtime_storage']
    memory_storage_inst = vault['memory_storage']

    module_group_index = collections.defaultdict(set)
    module_id_index = {}
    module_groups = runtime_storage_inst.get_by_key('module_groups') or {}

    for module_group in module_groups.values():
        module_group_name = module_group['module_group_name']
        module_group_id = module_group.get('id') or module_group_name.lower()

        module_id_index[module_group_id] = _make_module(
            module_group_id, module_group_name, module_group['modules'],
            module_group.get('tag') or 'group')

        for module in module_group['modules']:
            module_group_index[module].add(module_group_id)

    for module in memory_storage_inst.get_modules():
        module_id_index[module] = _make_module(module.lower(), module,
                                               [module.lower()], 'module')

    module_id_index['all'] = _make_module('all', 'All',
                                          memory_storage_inst.get_modules(),
                                          'project_type')

    vault['module_group_index'] = module_group_index
    vault['module_id_index'] = module_id_index


def init_project_types(vault):
    runtime_storage_inst = vault['runtime_storage']
    project_types = runtime_storage_inst.get_by_key('project_types') or {}

    result = []
    parent = None
    for pt in project_types:
        is_child = pt.get('child', False)
        if parent and is_child:
            item = {'id': pt['id'], 'text': pt['title']}
            if 'items' in parent:
                parent['items'].append(item)
            else:
                parent['items'] = [item]
        else:
            parent = pt
            result.append(parent)

    vault['project_types'] = result
    vault['project_types_index'] = dict([(pt['id'], pt)
                                         for pt in project_types])


def get_project_types():
    return get_vault()['project_types']


def get_release_options():
    runtime_storage_inst = get_vault()['runtime_storage']
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
    if not is_project_type_valid(project_type_id):
        return None
    return get_vault()['project_types_index'][project_type_id]


def get_user_from_runtime_storage(user_id):
    runtime_storage_inst = get_vault()['runtime_storage']
    return utils.load_user(runtime_storage_inst, user_id)


def resolve_modules(module_ids):
    module_id_index = get_vault().get('module_id_index') or {}
    modules = set()
    for module_id in module_ids:
        if module_id in module_id_index:
            modules |= set(module_id_index[module_id]['modules'])
    return modules


def resolve_project_types(project_types):
    modules = set()
    for pt in project_types:
        if is_project_type_valid(pt):
            modules |= resolve_modules(
                get_vault()['project_types_index'][pt]['modules'])
    return modules
