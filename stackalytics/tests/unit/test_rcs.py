# Copyright (c) 2015 Mirantis Inc.
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

import mock
import testtools

from stackalytics.processor import rcs

REVIEW_ONE = json.dumps(
    {"project": "openstack/nova", "branch": "master", "topic": "bug/1494374",
     "id": "Id741dfc769c02a5544691a7db49a7dbff6b11376", "number": "229382",
     "subject": "method is nearly 400 LOC and should be broken up",
     "createdOn": 1443613948, "lastUpdated": 1444222222,
     "sortKey": "0038481b00038006", "open": True, "status": "NEW"})
REVIEW_END_LINE = json.dumps(
    {"type": "stats", "rowCount": 2, "runTimeMilliseconds": 13})


class TestRcs(testtools.TestCase):

    @mock.patch('paramiko.SSHClient')
    def test_setup(self, mock_client_cons):
        mock_client = mock.Mock()
        mock_client_cons.return_value = mock_client

        mock_connect = mock.Mock()
        mock_client.connect = mock_connect

        gerrit = rcs.Gerrit('gerrit://review.openstack.org')
        gerrit.setup(username='user', key_filename='key')

        mock_connect.assert_called_once_with(
            'review.openstack.org', port=rcs.DEFAULT_PORT, key_filename='key',
            username='user')

    @mock.patch('paramiko.SSHClient')
    def test_setup_error(self, mock_client_cons):
        mock_client = mock.Mock()
        mock_client_cons.return_value = mock_client

        mock_connect = mock.Mock()
        mock_client.connect = mock_connect
        mock_connect.side_effect = Exception

        gerrit = rcs.Gerrit('gerrit://review.openstack.org')
        self.assertRaises(rcs.RcsException, gerrit.setup,
                          username='user', key_filename='key')

        mock_connect.assert_called_once_with(
            'review.openstack.org', port=rcs.DEFAULT_PORT, key_filename='key',
            username='user')

    @mock.patch('paramiko.SSHClient')
    @mock.patch('time.time')
    def test_log(self, mock_time, mock_client_cons):
        mock_client = mock.Mock()
        mock_client_cons.return_value = mock_client

        mock_exec = mock.Mock()
        mock_client.exec_command = mock_exec
        mock_exec.side_effect = [
            ('', [REVIEW_ONE, REVIEW_END_LINE], ''),  # one review and summary
            ('', [REVIEW_END_LINE], ''),  # only summary = no more reviews
        ]

        gerrit = rcs.Gerrit('uri')

        repo = dict(organization='openstack', module='nova')
        branch = 'master'
        last_retrieval_time = 1444000000
        mock_time.return_value = 1444333333
        records = list(gerrit.log(repo, branch, last_retrieval_time))

        self.assertEqual(1, len(records))
        self.assertEqual('229382', records[0]['number'])

        mock_client.exec_command.assert_has_calls([
            mock.call('gerrit query --all-approvals --patch-sets '
                      '--format JSON project:\'openstack/nova\' branch:master '
                      'limit:100 age:0s'),
            mock.call('gerrit query --all-approvals --patch-sets '
                      '--format JSON project:\'openstack/nova\' branch:master '
                      'limit:100 age:111111s'),
        ])

    @mock.patch('paramiko.SSHClient')
    def test_log_old_reviews(self, mock_client_cons):
        mock_client = mock.Mock()
        mock_client_cons.return_value = mock_client

        mock_exec = mock.Mock()
        mock_client.exec_command = mock_exec
        mock_exec.side_effect = [
            ('', [REVIEW_ONE, REVIEW_END_LINE], ''),  # one review and summary
            ('', [REVIEW_END_LINE], ''),  # only summary = no more reviews
        ]

        gerrit = rcs.Gerrit('uri')

        repo = dict(organization='openstack', module='nova')
        branch = 'master'
        last_retrieval_time = 1445000000
        records = list(gerrit.log(repo, branch, last_retrieval_time,
                                  status='merged', grab_comments=True))

        self.assertEqual(0, len(records))

        mock_client.exec_command.assert_has_calls([
            mock.call('gerrit query --all-approvals --patch-sets '
                      '--format JSON project:\'openstack/nova\' branch:master '
                      'limit:100 age:0s status:merged --comments'),
        ])

    @mock.patch('paramiko.SSHClient')
    @mock.patch('time.time')
    def test_log_error_tolerated(self, mock_time, mock_client_cons):
        mock_client = mock.Mock()
        mock_client_cons.return_value = mock_client

        mock_exec = mock.Mock()
        mock_client.exec_command = mock_exec
        mock_exec.side_effect = [
            Exception,
            ('', [REVIEW_ONE, REVIEW_END_LINE], ''),  # one review and summary
            Exception,
            ('', [REVIEW_END_LINE], ''),  # only summary = no more reviews
        ]

        gerrit = rcs.Gerrit('uri')

        repo = dict(organization='openstack', module='nova')
        branch = 'master'
        last_retrieval_time = 1444000000
        mock_time.return_value = 1444333333
        records = list(gerrit.log(repo, branch, last_retrieval_time))

        self.assertEqual(1, len(records))
        self.assertEqual('229382', records[0]['number'])

        mock_client.exec_command.assert_has_calls([
            mock.call('gerrit query --all-approvals --patch-sets '
                      '--format JSON project:\'openstack/nova\' branch:master '
                      'limit:100 age:0s'),
            mock.call('gerrit query --all-approvals --patch-sets '
                      '--format JSON project:\'openstack/nova\' branch:master '
                      'limit:100 age:111111s'),
        ])

    @mock.patch('paramiko.SSHClient')
    @mock.patch('time.time')
    def test_log_error_fatal(self, mock_time, mock_client_cons):
        mock_client = mock.Mock()
        mock_client_cons.return_value = mock_client

        mock_exec = mock.Mock()
        mock_client.exec_command = mock_exec
        mock_exec.side_effect = [Exception] * rcs.SSH_ERRORS_LIMIT

        gerrit = rcs.Gerrit('uri')

        repo = dict(organization='openstack', module='nova')
        branch = 'master'
        last_retrieval_time = 1444000000
        mock_time.return_value = 1444333333

        try:
            list(gerrit.log(repo, branch, last_retrieval_time))
            self.fail('Gerrit.log should raise RcsException, but it did not')
        except rcs.RcsException:
            pass

        mock_client.exec_command.assert_has_calls([
            mock.call('gerrit query --all-approvals --patch-sets '
                      '--format JSON project:\'openstack/nova\' branch:master '
                      'limit:100 age:0s')] * rcs.SSH_ERRORS_LIMIT)
