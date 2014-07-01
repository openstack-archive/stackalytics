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

import testtools

from stackalytics.processor import driverlog


class TestDriverlog(testtools.TestCase):
    def setUp(self):
        super(TestDriverlog, self).setUp()

    def test_find_ci_result_voting_ci(self):
        review = {
            'record_type': 'review',
            'id': 'I1045730e47e9e6ad31fcdfbaefdad77e2f3b2c3e',
            'module': 'nova',
            'branch': 'master',
            'status': 'NEW',
            'number': '97860',
            'patchSets': [
                {'number': '1',
                 'approvals': [
                     {'type': 'Verified', 'description': 'Verified',
                      'value': '1', 'grantedOn': 1234567890 - 1,
                      'by': {
                          'name': 'Batman',
                          'email': 'batman@openstack.org',
                          'username': 'batman'}},
                     {'type': 'Verified', 'description': 'Verified',
                      'value': '-1', 'grantedOn': 1234567890,
                      'by': {
                          'name': 'Pikachu',
                          'email': 'pikachu@openstack.org',
                          'username': 'pikachu'}},
                 ]}],
            'comments': [
                {'message': 'Patch Set 1: build successful',
                 'reviewer': {'username': 'batman'},
                 'timestamp': 1234567890}
            ]}

        ci_map = {
            'batman': {
                'name': 'Batman Driver',
                'vendor': 'Gotham Inc',
                'ci': {
                    'id': 'batman'
                }
            }
        }

        res = list(driverlog.find_ci_result(review, ci_map))

        expected_result = {
            'reviewer': {'username': 'batman'},
            'ci_result': True,
            'is_merged': False,
            'message': 'build successful',
            'date': 1234567890,
            'review_id': 'I1045730e47e9e6ad31fcdfbaefdad77e2f3b2c3e',
            'review_number': '97860',
            'driver_name': 'Batman Driver',
            'driver_vendor': 'Gotham Inc',
        }
        self.assertEqual(1, len(res), 'One CI result is expected')
        self.assertEqual(expected_result, res[0])
