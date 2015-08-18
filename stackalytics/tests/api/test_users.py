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


class TestAPIUsers(test_api.TestAPI):

    def test_users(self):
        with test_api.make_runtime_storage(
                {'repos': [
                    {'module': 'nova', 'organization': 'openstack',
                     'uri': 'git://git.openstack.org/openstack/nova.git'}],
                 'project_types': [
                     {'id': 'openstack', 'title': 'openstack',
                      'modules': ['nova', 'glance']}],
                 'releases': [{'release_name': 'prehistory',
                               'end_date': 1234567890},
                              {'release_name': 'icehouse',
                               'end_date': 1234567890}],
                 'module_groups': {
                     'nova': test_api.make_module('nova'),
                     'glance': test_api.make_module('glance')},
                 'user:john_doe': {'user_name': 'John Doe'},
                 'user:bill_smith': {'user_name': 'Bill Smith'}},
                test_api.make_records(record_type=['commit'], module=['nova'],
                                      user_id=['john_doe', 'bill_smith'])):
            response = self.app.get('/api/1.0/users?'
                                    'module=nova&metric=commits')
            users = test_api.load_json(response)['data']
            self.assertEqual(2, len(users))
            self.assertIn({'id': 'john_doe', 'text': 'John Doe'}, users)
            self.assertIn({'id': 'bill_smith', 'text': 'Bill Smith'}, users)

    def test_user_details(self):
        with test_api.make_runtime_storage(
                {'user:john_doe': {
                    'seq': 1, 'user_id': 'john_doe', 'user_name': 'John Doe',
                    'companies': [{'company_name': 'NEC', 'end_date': 0}],
                    'emails': 'john_doe@gmail.com'}},
                test_api.make_records(record_type=['commit'], module=['nova'],
                                      user_name=['John Doe', 'Bill Smith'])):
            response = self.app.get('/api/1.0/users/john_doe')
            user = test_api.load_json(response)['user']
            self.assertEqual('john_doe', user['user_id'])

    def test_user_not_found(self):
        with test_api.make_runtime_storage(
                {'user:john_doe': {
                    'seq': 1, 'user_id': 'john_doe', 'user_name': 'John Doe',
                    'companies': [{'company_name': 'NEC', 'end_date': 0}],
                    'emails': 'john_doe@gmail.com'},
                 'repos': [
                     {'module': 'nova', 'organization': 'openstack',
                      'uri': 'git://git.openstack.org/openstack/nova.git'}],
                 'module_groups': {'openstack': {
                     'module_group_name': 'openstack',
                     'modules': ['nova']}}},
                test_api.make_records(record_type=['commit'], module=['nova'],
                                      user_name=['John Doe', 'Bill Smith'])):
            response = self.app.get('/api/1.0/users/nonexistent')
            self.assertEqual(404, response.status_code)
