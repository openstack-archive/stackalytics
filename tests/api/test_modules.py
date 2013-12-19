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

import json

from tests.api import test_api


class TestAPIModules(test_api.TestAPI):

    def test_get_modules(self):
        with test_api.make_runtime_storage(
                {'repos': [{'module': 'nova', 'organization': 'openstack',
                            'uri': 'git://github.com/openstack/nova.git'},
                           {'module': 'glance', 'organization': 'openstack',
                            'uri': 'git://github.com/openstack/glance.git'}],
                 'module_groups': [
                     {'module_group_name': 'nova-group',
                      'modules': ['nova', 'python-novaclient']}]},
                test_api.make_records(record_type=['commit'],
                                      module=['glance', 'nova'])):

            response = self.app.get('/api/1.0/modules')
            modules = json.loads(response.data)['modules']
            self.assertEqual(
                [{'group': True, 'id': 'all', 'text': 'All',
                  'modules': ['glance', 'nova']},
                 {'id': 'glance', 'modules': ['glance'], 'text': 'glance'},
                 {'id': 'nova', 'modules': ['nova'], 'text': 'nova'},
                 {'group': True, 'id': 'nova-group', 'text': 'nova-group',
                  'modules': ['nova', 'python-novaclient']}], modules)

            response = self.app.get('/api/1.0/modules?module_name=glance')
            modules = json.loads(response.data)['modules']
            self.assertEqual(
                [{'id': 'glance', 'modules': ['glance'], 'text': 'glance'}],
                modules)

    def test_get_module(self):
        with test_api.make_runtime_storage(
                {'repos': [{'module': 'nova', 'organization': 'openstack',
                            'uri': 'git://github.com/openstack/nova.git'}],
                 'module_groups': [
                     {'module_group_name': 'nova-group',
                      'modules': ['nova', 'python-novaclient']}]},
                test_api.make_records(record_type=['commit'])):

            response = self.app.get('/api/1.0/modules/nova')
            module = json.loads(response.data)['module']
            self.assertEqual(
                {'id': 'nova', 'modules': ['nova'], 'text': 'nova'}, module)

            response = self.app.get('/api/1.0/modules/nova-group')
            module = json.loads(response.data)['module']
            self.assertEqual(
                {'group': True, 'id': 'nova-group', 'text': 'nova-group',
                 'modules': ['nova', 'python-novaclient']}, module)
