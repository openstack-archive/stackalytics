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


class TestAPIStats(test_api.TestAPI):

    def test_get_modules(self):
        with test_api.make_runtime_storage(
                {'repos': [{'module': 'nova', 'project_type': 'openstack',
                            'organization': 'openstack',
                            'uri': 'git://github.com/openstack/nova.git'},
                           {'module': 'glance', 'project_type': 'openstack',
                            'organization': 'openstack',
                            'uri': 'git://github.com/openstack/glance.git'}]},
                test_api.make_records(record_type=['commit'],
                                      loc=[10, 20, 30],
                                      module=['nova', 'glance']),
                test_api.make_records(record_type=['commit'],
                                      loc=[100, 200, 300],
                                      module=['glance'])):
            response = self.app.get('/api/1.0/stats/modules?metric=loc')
            stats = json.loads(response.data)['stats']
            self.assertEqual(2, len(stats))
            self.assertEqual(660, stats[0]['metric'])
            self.assertEqual('glance', stats[0]['id'])
            self.assertEqual(60, stats[1]['metric'])
            self.assertEqual('nova', stats[1]['id'])
