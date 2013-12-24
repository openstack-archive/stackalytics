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


class TestAPIReleases(test_api.TestAPI):

    def test_releases_empty(self):
        with test_api.make_runtime_storage({}):
            response = self.app.get('/api/1.0/releases')
            self.assertEqual(200, response.status_code)

    def test_releases(self):
        with test_api.make_runtime_storage(
                {'releases': [
                    {'release_name': 'prehistory', 'end_date': 1365033600},
                    {'release_name': 'havana', 'end_date': 1381968000},
                    {'release_name': 'icehouse', 'end_date': 1397692800}]}):
            response = self.app.get('/api/1.0/releases')
            releases = json.loads(response.data)['releases']
            self.assertEqual(3, len(releases))
            self.assertIn({'id': 'all', 'text': 'All'}, releases)
            self.assertIn({'id': 'icehouse', 'text': 'Icehouse'}, releases)

    def test_releases_search(self):
        with test_api.make_runtime_storage(
                {'releases': [
                    {'release_name': 'prehistory', 'end_date': 1365033600},
                    {'release_name': 'havana', 'end_date': 1381968000},
                    {'release_name': 'icehouse', 'end_date': 1397692800}]}):
            response = self.app.get('/api/1.0/releases?query=hav')
            releases = json.loads(response.data)['releases']
            self.assertEqual(1, len(releases))
            self.assertIn({'id': 'havana', 'text': 'Havana'}, releases)

    def test_release_details(self):
        with test_api.make_runtime_storage(
                {'releases': [
                    {'release_name': 'prehistory', 'end_date': 1365033600},
                    {'release_name': 'icehouse', 'end_date': 1397692800}]}):
            response = self.app.get('/api/1.0/releases/icehouse')
            release = json.loads(response.data)['release']
            self.assertEqual({'id': 'icehouse', 'text': 'Icehouse'}, release)
