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
import copy

import testtools

from stackalytics.processor import driverlog

COMMENT_SUCCESS = {
    'message': 'Patch Set 2: build successful',
    'reviewer': {'username': 'virt-ci'},
    'timestamp': 1234567890
}

COMMENT_FAILURE = {
    'message': 'Patch Set 2: build failed',
    'reviewer': {'username': 'virt-ci'},
    'timestamp': 1234567880
}

REVIEW = {
    'record_type': 'review',
    'id': 'I1045730e47e9e6ad31fcdfbaefdad77e2f3b2c3e',
    'module': 'nova',
    'branch': 'master',
    'status': 'MERGED',
    'number': '97860',
    'patchSets': [{'number': '1'}, {'number': '2'}],
    'comments': [
        {'message': 'Patch Set 2: build successful',
            'reviewer': {'username': 'other-ci'}, },
        {'message': 'Patch Set 2: job started',
            'reviewer': {'username': 'virt-ci'}, }]
}

DRIVER = {
    'name': 'Virt Nova Driver',
    'vendor': 'Virt Inc',
    'ci': {
        'id': 'virt-ci',
        'success_pattern': 'successful',
        'failure_pattern': 'failed',
    }
}

DRIVER_NON_EXISTENT = {
    'name': 'No Virt Nova Driver',
    'vendor': 'No Virt Inc',
    'ci': {
        'id': 'no-virt-ci',
        'success_pattern': 'successful',
        'failure_pattern': 'failed',
    }
}


class TestDriverlog(testtools.TestCase):
    def setUp(self):
        super(TestDriverlog, self).setUp()

    def test_find_ci_result_success(self):
        drivers = [DRIVER]
        review = copy.deepcopy(REVIEW)
        review['comments'].append(COMMENT_SUCCESS)

        res = list(driverlog.log([review], drivers))

        expected_result = {
            'user_id': 'ci:virt_nova_driver',
            'value': True,
            'message': 'build successful',
            'date': 1234567890,
            'branch': 'master',
            'review_id': 'I1045730e47e9e6ad31fcdfbaefdad77e2f3b2c3e',
            'review_number': '97860',
            'driver_name': 'Virt Nova Driver',
            'driver_vendor': 'Virt Inc',
            'module': 'nova',
        }
        self.assertEqual(1, len(res), 'One CI result is expected')
        self.assertEqual(expected_result, res[0])

    def test_find_ci_result_failure(self):
        drivers = [DRIVER]
        review = copy.deepcopy(REVIEW)
        review['comments'].append(COMMENT_FAILURE)

        res = list(driverlog.log([review], drivers))

        self.assertEqual(1, len(res), 'One CI result is expected')
        self.assertEqual(False, res[0]['value'])

    def test_find_ci_result_non_existent(self):
        drivers = [DRIVER_NON_EXISTENT]
        review = copy.deepcopy(REVIEW)
        review['comments'].append(COMMENT_SUCCESS)

        res = list(driverlog.log([REVIEW], drivers))

        self.assertEqual(0, len(res), 'No CI results expected')

    def test_find_ci_result_last_vote_only(self):
        # there may be multiple comments from the same CI,
        # only the last one is important
        drivers = [DRIVER]

        review = copy.deepcopy(REVIEW)
        review['comments'].append(COMMENT_FAILURE)
        review['comments'].append(COMMENT_SUCCESS)

        res = list(driverlog.log([review], drivers))

        self.assertEqual(1, len(res), 'One CI result is expected')
        self.assertEqual(True, res[0]['value'])
