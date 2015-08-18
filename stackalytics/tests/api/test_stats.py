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

from stackalytics.tests.api import test_api


class TestAPIStats(test_api.TestAPI):

    def test_get_modules(self):
        with test_api.make_runtime_storage(
                {
                    'repos': [
                        {'module': 'nova', 'organization': 'openstack',
                         'uri': 'git://git.openstack.org/openstack/nova.git'},
                        {'module': 'glance', 'organization': 'openstack',
                         'uri': 'git://git.openstack.org/openstack/glance.git'}
                    ],
                    'releases': [{'release_name': 'prehistory',
                                  'end_date': 1234567890},
                                 {'release_name': 'icehouse',
                                  'end_date': 1234567890}],
                    'module_groups': {
                        'openstack': {'id': 'openstack',
                                      'module_group_name': 'openstack',
                                      'modules': ['nova', 'glance'],
                                      'tag': 'group'},
                        'nova': test_api.make_module('nova'),
                        'glance': test_api.make_module('glance'),
                    },
                    'project_types': [
                        {'id': 'all', 'title': 'All',
                         'modules': ['nova', 'glance']}]},
                test_api.make_records(record_type=['commit'],
                                      loc=[10, 20, 30],
                                      module=['nova']),
                test_api.make_records(record_type=['commit'],
                                      loc=[100, 200, 300],
                                      module=['glance'])):
            response = self.app.get('/api/1.0/stats/modules?metric=loc&'
                                    'project_type=all')
            stats = test_api.load_json(response)['stats']
            self.assertEqual(2, len(stats))
            self.assertEqual(600, stats[0]['metric'])
            self.assertEqual('glance', stats[0]['id'])
            self.assertEqual(60, stats[1]['metric'])
            self.assertEqual('nova', stats[1]['id'])

    def test_get_engineers(self):
        with test_api.make_runtime_storage(
                {
                    'repos': [
                        {'module': 'nova', 'project_type': 'openstack',
                         'organization': 'openstack',
                         'uri': 'git://git.openstack.org/openstack/nova.git'},
                        {'module': 'glance', 'project_type': 'openstack',
                         'organization': 'openstack',
                         'uri': 'git://git.openstack.org/openstack/glance.git'}
                    ],
                    'releases': [{'release_name': 'prehistory',
                                  'end_date': 1234567890},
                                 {'release_name': 'icehouse',
                                  'end_date': 1234567890}],
                    'module_groups': {
                        'openstack': {'id': 'openstack',
                                      'module_group_name': 'openstack',
                                      'modules': ['nova', 'glance'],
                                      'tag': 'group'},
                        'nova': test_api.make_module('nova'),
                        'glance': test_api.make_module('glance'),
                    },
                    'project_types': [
                        {'id': 'all', 'title': 'All',
                         'modules': ['nova', 'glance']}],
                    'user:john_doe': {
                        'seq': 1, 'user_id': 'john_doe',
                        'user_name': 'John Doe',
                        'companies': [{'company_name': 'NEC', 'end_date': 0}],
                        'emails': ['john_doe@gmail.com'], 'core': []},
                    'user:bill': {
                        'seq': 1, 'user_id': 'bill', 'user_name': 'Bill Smith',
                        'companies': [{'company_name': 'IBM', 'end_date': 0}],
                        'emails': ['bill_smith@gmail.com'], 'core': []}},
                test_api.make_records(record_type=['commit'],
                                      loc=[10, 20, 30],
                                      module=['nova'],
                                      user_id=['john_doe']),
                test_api.make_records(record_type=['commit'],
                                      loc=[100, 200, 300],
                                      module=['glance'],
                                      user_id=['john_doe']),
                test_api.make_records(record_type=['review'],
                                      primary_key=['0123456789'],
                                      module=['glance']),
                test_api.make_records(record_type=['mark'],
                                      review_id=['0123456789'],
                                      module=['glance'],
                                      user_id=['john_doe', 'bill'])):
            response = self.app.get('/api/1.0/stats/engineers?metric=loc&'
                                    'project_type=all')
            stats = test_api.load_json(response)['stats']
            self.assertEqual(1, len(stats))
            self.assertEqual(660, stats[0]['metric'])

    def test_get_engineers_extended(self):
        with test_api.make_runtime_storage(
                {
                    'repos': [
                        {'module': 'nova', 'project_type': 'openstack',
                         'organization': 'openstack',
                         'uri': 'git://git.openstack.org/openstack/nova.git'},
                        {'module': 'glance', 'project_type': 'openstack',
                         'organization': 'openstack',
                         'uri': 'git://git.openstack.org/openstack/glance.git'}
                    ],
                    'releases': [{'release_name': 'prehistory',
                                  'end_date': 1234567890},
                                 {'release_name': 'icehouse',
                                  'end_date': 1234567890}],
                    'module_groups': {
                        'openstack': {'id': 'openstack',
                                      'module_group_name': 'openstack',
                                      'modules': ['nova', 'glance'],
                                      'tag': 'group'},
                        'nova': test_api.make_module('nova'),
                        'glance': test_api.make_module('glance'),
                    },
                    'project_types': [
                        {'id': 'all', 'title': 'All',
                         'modules': ['nova', 'glance']}],
                    'user:john_doe': {
                        'seq': 1, 'user_id': 'john_doe',
                        'user_name': 'John Doe',
                        'companies': [{'company_name': 'NEC', 'end_date': 0}],
                        'emails': ['john_doe@gmail.com'], 'core': []},
                    'user:smith': {
                        'seq': 1, 'user_id': 'smith',
                        'user_name': 'Bill Smith',
                        'companies': [{'company_name': 'IBM', 'end_date': 0}],
                        'emails': ['bill_smith@gmail.com'], 'core': []}},
                test_api.make_records(record_type=['commit'],
                                      loc=[10, 20, 30],
                                      module=['nova'],
                                      user_id=['john_doe']),
                test_api.make_records(record_type=['review'],
                                      primary_key=['0123456789', '9876543210'],
                                      module=['glance']),
                test_api.make_records(record_type=['mark'],
                                      review_id=['0123456789', '9876543210'],
                                      module=['glance'],
                                      value=[1],
                                      type=['Code-Review'],
                                      author_name=['John Doe'],
                                      user_id=['john_doe']),
                test_api.make_records(record_type=['mark'],
                                      review_id=['0123456789'],
                                      module=['glance'],
                                      author_name=['Bill Smith'],
                                      user_id=['smith'])):
            response = self.app.get('/api/1.0/stats/engineers_extended?'
                                    'project_type=all')
            stats = test_api.load_json(response)['stats']
            self.assertEqual(2, len(stats))
            self.assertEqual(2, stats[0]['mark'])
            self.assertEqual('john_doe', stats[0]['id'])
            self.assertEqual(3, stats[0]['commit'])
            self.assertEqual(2, stats[0]['1'])
