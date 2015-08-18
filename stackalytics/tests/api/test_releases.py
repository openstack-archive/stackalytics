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


class TestAPIReleases(test_api.TestAPI):

    def test_releases(self):
        with test_api.make_runtime_storage(
                {'releases': [
                    {'release_name': 'prehistory', 'end_date': 1365033600},
                    {'release_name': 'havana', 'end_date': 1381968000},
                    {'release_name': 'icehouse', 'end_date': 1397692800}],
                 'project_types': [
                     {'id': 'all', 'title': 'All',
                      'modules': ['nova', 'glance', 'nova-cli']},
                     {'id': 'openstack', 'title': 'OpenStack',
                      'modules': ['nova', 'glance']}]},
                test_api.make_records(record_type=['commit'])):
            response = self.app.get('/api/1.0/releases')
            releases = test_api.load_json(response)['data']
            self.assertEqual(3, len(releases))
            self.assertIn({'id': 'all', 'text': 'All'}, releases)
            self.assertIn({'id': 'icehouse', 'text': 'Icehouse'}, releases)
