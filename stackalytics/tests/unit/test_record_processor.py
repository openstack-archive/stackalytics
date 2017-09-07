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

import time

import mock
from oslo_config import cfg
import six
import testtools

from stackalytics.processor import config
from stackalytics.processor import record_processor
from stackalytics.processor import runtime_storage
from stackalytics.processor import user_processor
from stackalytics.processor.user_processor import get_company_by_email
from stackalytics.processor import utils


CONF = cfg.CONF

RELEASES = [
    {
        'release_name': 'prehistory',
        'end_date': utils.date_to_timestamp('2011-Apr-21')
    },
    {
        'release_name': 'Diablo',
        'end_date': utils.date_to_timestamp('2011-Sep-08')
    },
    {
        'release_name': 'Zoo',
        'end_date': utils.date_to_timestamp('2035-Sep-08')
    },
]

REPOS = [
    {
        "branches": ["master"],
        "module": "stackalytics",
        "project_type": "stackforge",
        "uri": "git://git.openstack.org/stackforge/stackalytics.git"
    }
]


class TestRecordProcessor(testtools.TestCase):
    def setUp(self):
        super(TestRecordProcessor, self).setUp()
        self.read_json_from_uri_patch = mock.patch(
            'stackalytics.processor.utils.read_json_from_uri')
        self.read_launchpad = self.read_json_from_uri_patch.start()
        self.lp_profile_by_launchpad_id_patch = mock.patch(
            'stackalytics.processor.launchpad_utils.'
            '_lp_profile_by_launchpad_id')
        self.lp_profile_by_launchpad_id = (
            self.lp_profile_by_launchpad_id_patch.start())
        self.lp_profile_by_launchpad_id.return_value = None
        self.lp_profile_by_email_patch = mock.patch(
            'stackalytics.processor.launchpad_utils._lp_profile_by_email')
        self.lp_profile_by_email = (
            self.lp_profile_by_email_patch.start())
        self.lp_profile_by_email.return_value = None
        CONF.register_opts(config.CONNECTION_OPTS + config.PROCESSOR_OPTS)

    def tearDown(self):
        super(TestRecordProcessor, self).tearDown()
        self.read_json_from_uri_patch.stop()
        self.lp_profile_by_launchpad_id_patch.stop()
        self.lp_profile_by_email_patch.stop()

    # get_company_by_email

    def test_get_company_by_email_mapped(self):
        record_processor_inst = self.make_record_processor(
            companies=[{'company_name': 'IBM', 'domains': ['ibm.com']}]
        )
        email = 'jdoe@ibm.com'
        res = get_company_by_email(record_processor_inst.domains_index, email)
        self.assertEqual('IBM', res)

    def test_get_company_by_email_with_long_suffix_mapped(self):
        record_processor_inst = self.make_record_processor(
            companies=[{'company_name': 'NEC', 'domains': ['nec.co.jp']}]
        )
        email = 'man@mxw.nes.nec.co.jp'
        res = get_company_by_email(record_processor_inst.domains_index, email)
        self.assertEqual('NEC', res)

    def test_get_company_by_email_with_long_suffix_mapped_2(self):
        record_processor_inst = self.make_record_processor(
            companies=[{'company_name': 'NEC',
                        'domains': ['nec.co.jp', 'nec.com']}]
        )
        email = 'man@mxw.nes.nec.com'
        res = get_company_by_email(record_processor_inst.domains_index, email)
        self.assertEqual('NEC', res)

    def test_get_company_by_email_not_mapped(self):
        record_processor_inst = self.make_record_processor()
        email = 'foo@boo.com'
        res = get_company_by_email(record_processor_inst.domains_index, email)
        self.assertIsNone(res)

    # commit processing

    def test_process_commit_existing_user(self):
        record_processor_inst = self.make_record_processor(
            users=[
                {
                    'user_id': 'john_doe',
                    'launchpad_id': 'john_doe',
                    'user_name': 'John Doe',
                    'emails': ['johndoe@gmail.com', 'johndoe@nec.co.jp'],
                    'companies': [
                        {'company_name': '*independent',
                         'end_date': 1234567890},
                        {'company_name': 'NEC',
                         'end_date': 0},
                    ]
                }
            ])

        processed_commit = list(record_processor_inst.process(
            generate_commits(author_email='johndoe@gmail.com',
                             author_name='John Doe')))[0]

        expected_commit = {
            'user_id': 'john_doe',
            'author_email': 'johndoe@gmail.com',
            'author_name': 'John Doe',
            'company_name': 'NEC',
        }

        self.assertRecordsMatch(expected_commit, processed_commit)

    def test_process_commit_existing_user_old_job(self):
        record_processor_inst = self.make_record_processor(
            users=[
                {
                    'user_id': 'john_doe',
                    'launchpad_id': 'john_doe',
                    'user_name': 'John Doe',
                    'emails': ['johndoe@gmail.com', 'johndoe@nec.co.jp'],
                    'companies': [
                        {'company_name': '*independent',
                         'end_date': 1234567890},
                        {'company_name': 'NEC',
                         'end_date': 0},
                    ]
                }
            ])

        processed_commit = list(record_processor_inst.process(
            generate_commits(author_email='johndoe@gmail.com',
                             author_name='John Doe',
                             date=1000000000)))[0]

        expected_commit = {
            'user_id': 'john_doe',
            'author_email': 'johndoe@gmail.com',
            'author_name': 'John Doe',
            'company_name': '*independent',
        }

        self.assertRecordsMatch(expected_commit, processed_commit)

    def test_process_commit_existing_user_new_email_known_company(self):
        # User is known to LP, his email is new to us, and maps to other
        # company. Should return other company instead of those mentioned
        # in user profile
        record_processor_inst = self.make_record_processor(
            users=[
                {'user_id': 'john_doe',
                 'launchpad_id': 'john_doe',
                 'user_name': 'John Doe',
                 'emails': ['johndoe@nec.co.jp'],
                 'companies': [{'company_name': 'NEC', 'end_date': 0}]}
            ],
            companies=[{'company_name': 'IBM', 'domains': ['ibm.com']}],
            lp_info={'johndoe@ibm.com':
                     {'name': 'john_doe', 'display_name': 'John Doe'}})

        processed_commit = list(record_processor_inst.process(
            generate_commits(author_email='johndoe@ibm.com',
                             author_name='John Doe')))[0]

        expected_commit = {
            'user_id': 'john_doe',
            'author_email': 'johndoe@ibm.com',
            'author_name': 'John Doe',
            'company_name': 'IBM',
        }

        self.assertRecordsMatch(expected_commit, processed_commit)
        self.assertIn('johndoe@ibm.com', user_processor.load_user(
            record_processor_inst.runtime_storage_inst,
            user_id='john_doe')['emails'])

    def test_process_commit_existing_user_new_email_known_company_static(self):
        # User profile is configured in default_data. Email is new to us,
        # and maps to other company. We still use a company specified
        # in the profile
        record_processor_inst = self.make_record_processor(
            users=[
                {'user_id': 'john_doe',
                 'launchpad_id': 'john_doe',
                 'user_name': 'John Doe',
                 'static': True,
                 'emails': ['johndoe@nec.co.jp'],
                 'companies': [{'company_name': 'NEC', 'end_date': 0}]}
            ],
            companies=[{'company_name': 'IBM', 'domains': ['ibm.com']}],
            lp_info={'johndoe@ibm.com':
                     {'name': 'john_doe', 'display_name': 'John Doe'}})

        processed_commit = list(record_processor_inst.process(
            generate_commits(author_email='johndoe@ibm.com',
                             author_name='John Doe')))[0]

        expected_commit = {
            'user_id': 'john_doe',
            'author_email': 'johndoe@ibm.com',
            'author_name': 'John Doe',
            'company_name': 'NEC',
        }

        self.assertRecordsMatch(expected_commit, processed_commit)
        self.assertIn('johndoe@ibm.com', user_processor.load_user(
            record_processor_inst.runtime_storage_inst,
            user_id='john_doe')['emails'])

    def test_process_commit_existing_user_old_job_not_overridden(self):
        # User is known to LP, his email is new to us, and maps to other
        # company. Have some record with new email, but from the period when
        # he worked for other company. Should return other company as mentioned
        # in profile instead of overriding
        record_processor_inst = self.make_record_processor(
            users=[
                {'user_id': 'john_doe',
                 'launchpad_id': 'john_doe',
                 'user_name': 'John Doe',
                 'emails': ['johndoe@nec.co.jp'],
                 'companies': [{'company_name': 'IBM', 'end_date': 1200000000},
                               {'company_name': 'NEC', 'end_date': 0}]}
            ],
            companies=[{'company_name': 'IBM', 'domains': ['ibm.com']},
                       {'company_name': 'NEC', 'domains': ['nec.com']}],
            lp_info={'johndoe@nec.com':
                     {'name': 'john_doe', 'display_name': 'John Doe'}})

        processed_commit = list(record_processor_inst.process(
            generate_commits(author_email='johndoe@nec.com',
                             author_name='John Doe',
                             date=1000000000)))[0]

        expected_commit = {
            'user_id': 'john_doe',
            'author_email': 'johndoe@nec.com',
            'author_name': 'John Doe',
            'company_name': 'IBM',
        }

        self.assertRecordsMatch(expected_commit, processed_commit)

    def test_process_commit_existing_user_new_email_unknown_company(self):
        # User is known to LP, but his email is new to us. Should match
        # the user and return company from user profile
        record_processor_inst = self.make_record_processor(
            users=[
                {'user_id': 'john_doe',
                 'launchpad_id': 'john_doe',
                 'user_name': 'John Doe',
                 'emails': ['johndoe@nec.co.jp'],
                 'companies': [{'company_name': 'NEC', 'end_date': 0}]}
            ],
            companies=[{'company_name': 'IBM', 'domains': ['ibm.com']}],
            lp_info={'johndoe@gmail.com':
                     {'name': 'john_doe', 'display_name': 'John Doe'}})

        processed_commit = list(record_processor_inst.process(
            generate_commits(author_email='johndoe@gmail.com',
                             author_name='John Doe')))[0]

        expected_commit = {
            'user_id': 'john_doe',
            'author_email': 'johndoe@gmail.com',
            'author_name': 'John Doe',
            'company_name': 'NEC',
        }

        self.assertRecordsMatch(expected_commit, processed_commit)
        self.assertIn('johndoe@gmail.com', user_processor.load_user(
            record_processor_inst.runtime_storage_inst,
            user_id='john_doe')['emails'])

    def test_process_commit_existing_user_new_email_known_company_update(self):
        record_processor_inst = self.make_record_processor(
            users=[
                {'user_id': 'john_doe',
                 'launchpad_id': 'john_doe',
                 'user_name': 'John Doe',
                 'emails': ['johndoe@gmail.com'],
                 'companies': [{'company_name': '*independent',
                                'end_date': 0}]}
            ],
            companies=[{'company_name': 'IBM', 'domains': ['ibm.com']}],
            lp_info={'johndoe@ibm.com':
                     {'name': 'john_doe', 'display_name': 'John Doe'}})

        processed_commit = list(record_processor_inst.process(
            generate_commits(author_email='johndoe@ibm.com',
                             author_name='John Doe')))[0]

        expected_commit = {
            'user_id': 'john_doe',
            'author_email': 'johndoe@ibm.com',
            'author_name': 'John Doe',
            'company_name': 'IBM',
        }

        self.assertRecordsMatch(expected_commit, processed_commit)
        user = user_processor.load_user(
            record_processor_inst.runtime_storage_inst, user_id='john_doe')
        self.assertIn('johndoe@gmail.com', user['emails'])
        self.assertEqual('IBM', user['companies'][0]['company_name'],
                         message='User affiliation should be updated')

    def test_process_commit_new_user(self):
        # User is known to LP, but new to us
        # Should add new user and set company depending on email
        record_processor_inst = self.make_record_processor(
            companies=[{'company_name': 'IBM', 'domains': ['ibm.com']}],
            lp_info={'johndoe@ibm.com':
                     {'name': 'john_doe', 'display_name': 'John Doe'}})

        processed_commit = list(record_processor_inst.process(
            generate_commits(author_email='johndoe@ibm.com',
                             author_name='John Doe')))[0]

        expected_commit = {
            'user_id': 'john_doe',
            'author_email': 'johndoe@ibm.com',
            'author_name': 'John Doe',
            'company_name': 'IBM',
        }

        self.assertRecordsMatch(expected_commit, processed_commit)
        user = user_processor.load_user(
            record_processor_inst.runtime_storage_inst, user_id='john_doe')
        self.assertIn('johndoe@ibm.com', user['emails'])
        self.assertEqual('IBM', user['companies'][0]['company_name'])

    def test_process_commit_new_user_unknown_to_lb(self):
        # User is new to us and not known to LP
        # Should set user name and empty LPid
        record_processor_inst = self.make_record_processor(
            companies=[{'company_name': 'IBM', 'domains': ['ibm.com']}])

        processed_commit = list(record_processor_inst.process(
            generate_commits(author_email='johndoe@ibm.com',
                             author_name='John Doe')))[0]

        expected_commit = {
            'launchpad_id': None,
            'author_email': 'johndoe@ibm.com',
            'author_name': 'John Doe',
            'company_name': 'IBM',
        }

        self.assertRecordsMatch(expected_commit, processed_commit)
        user = user_processor.load_user(
            record_processor_inst.runtime_storage_inst,
            user_id='johndoe@ibm.com')
        self.assertIn('johndoe@ibm.com', user['emails'])
        self.assertEqual('IBM', user['companies'][0]['company_name'])
        self.assertIsNone(user['launchpad_id'])

    def test_process_review_new_user(self):
        # User is known to LP, but new to us
        # Should add new user and set company depending on email
        record_processor_inst = self.make_record_processor(
            companies=[{'company_name': 'IBM', 'domains': ['ibm.com']}],
            lp_info={'johndoe@ibm.com':
                     {'name': 'john_doe', 'display_name': 'John Doe'}})

        processed_review = list(record_processor_inst.process([
            {'record_type': 'review',
             'id': 'I1045730e47e9e6ad31fcdfbaefdad77e2f3b2c3e',
             'subject': 'Fix AttributeError in Keypair._add_details()',
             'owner': {'name': 'John Doe',
                       'email': 'johndoe@ibm.com',
                       'username': 'John_Doe'},
             'createdOn': 1379404951,
             'module': 'nova', 'branch': 'master'}
        ]))[0]

        expected_review = {
            'user_id': 'john_doe',
            'author_email': 'johndoe@ibm.com',
            'author_name': 'John Doe',
            'company_name': 'IBM',
        }

        self.assertRecordsMatch(expected_review, processed_review)
        user = user_processor.load_user(
            record_processor_inst.runtime_storage_inst, user_id='john_doe')
        self.assertEqual('John_Doe', user['gerrit_id'])

    def test_process_review_without_name(self):
        record_processor_inst = self.make_record_processor()

        records = list(record_processor_inst.process([
            {
                'record_type': 'review',
                'module': 'sandbox',
                "project": "openstack-dev/sandbox",
                "branch": "master",
                "id": "I8ecdd044c45e93589b42c3166167c30a3bd0ed5f",
                "number": "220784", "subject": "hello,i will commit",
                "owner": {"email": "1102012941@qq.com", "username": "yl"},
                "createdOn": 1441524597,
                "patchSets": [
                    {
                        "number": "1",
                        "revision": "95f73967a869db6748b22c6562fbfc09c08ef910",
                        "uploader": {
                            "email": "foo@qq.com"},
                        "createdOn": 1441524597,
                        "author": {
                            "email": "1102012941@qq.com"},
                        "approvals": [
                            {"type": "Code-Review",
                             "value": "-1",
                             "grantedOn": 1441524601,
                             "by": {
                                 "email": "congressci@gmail.com",
                                 "username": "vmware-congress-ci"}}]}]}
        ]))

        expected_review = {
            'user_id': 'yl',
            'author_email': '1102012941@qq.com',
            'author_name': 'yl',
            'company_name': '*independent',
        }

        expected_patch = {
            'user_id': 'foo@qq.com',
            'author_email': 'foo@qq.com',
            'author_name': 'Anonymous Coward',
            'company_name': '*independent',
        }

        expected_mark = {
            'user_id': 'vmware-congress-ci',
            'author_email': 'congressci@gmail.com',
            'author_name': 'vmware-congress-ci',
            'company_name': '*independent',
        }

        self.assertRecordsMatch(expected_review, records[0])
        self.assertRecordsMatch(expected_patch, records[1])
        self.assertRecordsMatch(expected_mark, records[2])

    def generate_bugs(self, status='Confirmed', **kwargs):
        rec = {
            'record_type': 'bug',
            'id': 'bug_id',
            'owner': 'owner',
            'date_created': 1234567890,
            'module': 'nova',
            'status': status
        }
        rec.update(kwargs)
        yield rec

    def test_process_bug_not_fixed(self):
        record = self.generate_bugs()
        record_processor_inst = self.make_record_processor()
        bugs = list(record_processor_inst.process(record))
        self.assertEqual(len(bugs), 1)
        self.assertRecordsMatch({
            'primary_key': 'bugf:bug_id',
            'record_type': 'bugf',
            'launchpad_id': 'owner',
            'date': 1234567890,
        }, bugs[0])

    def test_process_bug_fix_committed(self):
        record = self.generate_bugs(status='Fix Committed',
                                    date_fix_committed=1234567891,
                                    assignee='assignee')
        record_processor_inst = self.make_record_processor()
        bugs = list(record_processor_inst.process(record))
        self.assertEqual(len(bugs), 2)
        self.assertRecordsMatch({
            'primary_key': 'bugf:bug_id',
            'record_type': 'bugf',
            'launchpad_id': 'owner',
            'date': 1234567890,
        }, bugs[0])
        self.assertRecordsMatch({
            'primary_key': 'bugr:bug_id',
            'record_type': 'bugr',
            'launchpad_id': 'assignee',
            'date': 1234567891,
        }, bugs[1])

    def test_process_bug_fix_released(self):
        record = self.generate_bugs(status='Fix Released',
                                    date_fix_committed=1234567891,
                                    date_fix_released=1234567892,
                                    assignee='assignee')
        record_processor_inst = self.make_record_processor()
        bugs = list(record_processor_inst.process(record))
        self.assertEqual(len(bugs), 2)
        self.assertRecordsMatch({
            'primary_key': 'bugf:bug_id',
            'record_type': 'bugf',
            'launchpad_id': 'owner',
            'date': 1234567890,
        }, bugs[0])
        self.assertRecordsMatch({
            'primary_key': 'bugr:bug_id',
            'record_type': 'bugr',
            'launchpad_id': 'assignee',
            'date': 1234567891,
        }, bugs[1])

    def test_process_bug_fix_released_without_committed(self):
        record = self.generate_bugs(status='Fix Released',
                                    date_fix_released=1234567892,
                                    assignee='assignee')
        record_processor_inst = self.make_record_processor()
        bugs = list(record_processor_inst.process(record))
        self.assertEqual(len(bugs), 2)
        self.assertRecordsMatch({
            'primary_key': 'bugf:bug_id',
            'record_type': 'bugf',
            'launchpad_id': 'owner',
            'date': 1234567890,
        }, bugs[0])
        self.assertRecordsMatch({
            'primary_key': 'bugr:bug_id',
            'record_type': 'bugr',
            'launchpad_id': 'assignee',
            'date': 1234567892,
        }, bugs[1])

    def test_process_bug_fix_committed_without_assignee(self):
        record = self.generate_bugs(status='Fix Committed',
                                    date_fix_committed=1234567891)
        record_processor_inst = self.make_record_processor()
        bugs = list(record_processor_inst.process(record))
        self.assertEqual(len(bugs), 2)
        self.assertRecordsMatch({
            'primary_key': 'bugf:bug_id',
            'record_type': 'bugf',
            'launchpad_id': 'owner',
            'date': 1234567890,
        }, bugs[0])
        self.assertRecordsMatch({
            'primary_key': 'bugr:bug_id',
            'record_type': 'bugr',
            'launchpad_id': '*unassigned',
            'date': 1234567891,
        }, bugs[1])

    # process records complex scenarios

    def test_process_blueprint_one_draft_spawned_lp_doesnt_know_user(self):
        # In: blueprint record
        #     LP doesn't know user
        # Out: blueprint-draft record
        #      new user profile created
        record_processor_inst = self.make_record_processor()

        processed_records = list(record_processor_inst.process([
            {'record_type': 'bp',
             'id': 'mod:blueprint',
             'self_link': 'http://launchpad.net/blueprint',
             'owner': 'john_doe',
             'date_created': 1234567890}
        ]))

        self.assertRecordsMatch(
            {'record_type': 'bpd',
             'launchpad_id': 'john_doe',
             'author_name': 'john_doe',
             'company_name': '*independent'},
            processed_records[0])

        user = user_processor.load_user(
            record_processor_inst.runtime_storage_inst, user_id='john_doe')
        self.assertEqual({
            'seq': 1,
            'user_id': 'john_doe',
            'launchpad_id': 'john_doe',
            'user_name': 'john_doe',
            'emails': [],
            'companies': [{'company_name': '*independent', 'end_date': 0}]
        }, user)

    def test_process_blueprint_one_draft_spawned_lp_knows_user(self):
        # In: blueprint record
        #     LP knows user
        # Out: blueprint-draft record
        #      new user profile created, name is taken from LP profile
        record_processor_inst = self.make_record_processor(
            lp_user_name={
                'john_doe': {'name': 'john_doe', 'display_name': 'John Doe'}})

        processed_records = list(record_processor_inst.process([
            {'record_type': 'bp',
             'id': 'mod:blueprint',
             'self_link': 'http://launchpad.net/blueprint',
             'owner': 'john_doe',
             'date_created': 1234567890}
        ]))

        self.assertRecordsMatch(
            {'record_type': 'bpd',
             'launchpad_id': 'john_doe',
             'author_name': 'John Doe',
             'company_name': '*independent'},
            processed_records[0])

        user = user_processor.load_user(
            record_processor_inst.runtime_storage_inst, user_id='john_doe')
        self.assertEqual({
            'seq': 1,
            'user_id': 'john_doe',
            'launchpad_id': 'john_doe',
            'user_name': 'John Doe',
            'emails': [],
            'companies': [{'company_name': '*independent', 'end_date': 0}]
        }, user)

    def test_process_blueprint_then_review(self):
        record_processor_inst = self.make_record_processor(
            lp_user_name={
                'john_doe': {'name': 'john_doe', 'display_name': 'John Doe'}})

        processed_records = list(record_processor_inst.process([
            {'record_type': 'bp',
             'id': 'mod:blueprint',
             'self_link': 'http://launchpad.net/blueprint',
             'owner': 'john_doe',
             'date_created': 1234567890},
            {'record_type': 'review',
             'id': 'I1045730e47e9e6ad31fcdfbaefdad77e2f3b2c3e',
             'subject': 'Fix AttributeError in Keypair._add_details()',
             'owner': {'name': 'John Doe',
                       'email': 'john_doe@gmail.com',
                       'username': 'john_doe'},
             'createdOn': 1379404951,
             'module': 'nova', 'branch': 'master'}
        ]))

        self.assertRecordsMatch(
            {'record_type': 'bpd',
             'user_id': 'john_doe',
             'author_name': 'John Doe',
             'company_name': '*independent'},
            processed_records[0])

        self.assertRecordsMatch(
            {'record_type': 'review',
             'user_id': 'john_doe',
             'author_name': 'John Doe',
             'author_email': 'john_doe@gmail.com',
             'company_name': '*independent'},
            processed_records[1])

        user = {'seq': 1,
                'user_id': 'john_doe',
                'launchpad_id': 'john_doe',
                'gerrit_id': 'john_doe',
                'user_name': 'John Doe',
                'emails': ['john_doe@gmail.com'],
                'companies': [{'company_name': '*independent', 'end_date': 0}]}
        self.assertEqual(user, user_processor.load_user(
            record_processor_inst.runtime_storage_inst,
            user_id='john_doe'))
        self.assertEqual(user, user_processor.load_user(
            record_processor_inst.runtime_storage_inst,
            email='john_doe@gmail.com'))

    def test_process_blueprint_then_commit(self):
        record_processor_inst = self.make_record_processor(
            lp_user_name={
                'john_doe': {'name': 'john_doe', 'display_name': 'John Doe'}},
            lp_info={'john_doe@gmail.com':
                     {'name': 'john_doe', 'display_name': 'John Doe'}})

        processed_records = list(record_processor_inst.process([
            {'record_type': 'bp',
             'id': 'mod:blueprint',
             'self_link': 'http://launchpad.net/blueprint',
             'owner': 'john_doe',
             'date_created': 1234567890},
            {'record_type': 'commit',
             'commit_id': 'de7e8f297c193fb310f22815334a54b9c76a0be1',
             'author_name': 'John Doe',
             'author_email': 'john_doe@gmail.com',
             'date': 1234567890,
             'lines_added': 25,
             'lines_deleted': 9,
             'release_name': 'havana'}
        ]))

        self.assertRecordsMatch(
            {'record_type': 'bpd',
             'launchpad_id': 'john_doe',
             'author_name': 'John Doe',
             'company_name': '*independent'},
            processed_records[0])

        self.assertRecordsMatch(
            {'record_type': 'commit',
             'user_id': 'john_doe',
             'author_name': 'John Doe',
             'author_email': 'john_doe@gmail.com',
             'company_name': '*independent'},
            processed_records[1])

        user = {'seq': 1,
                'user_id': 'john_doe',
                'launchpad_id': 'john_doe',
                'user_name': 'John Doe',
                'emails': ['john_doe@gmail.com'],
                'companies': [{'company_name': '*independent', 'end_date': 0}]}
        self.assertEqual(user, user_processor.load_user(
            record_processor_inst.runtime_storage_inst,
            user_id='john_doe'))
        self.assertEqual(user, user_processor.load_user(
            record_processor_inst.runtime_storage_inst,
            email='john_doe@gmail.com'))

    def test_process_review_then_blueprint(self):
        record_processor_inst = self.make_record_processor(
            lp_user_name={
                'john_doe': {'name': 'john_doe', 'display_name': 'John Doe'}})

        processed_records = list(record_processor_inst.process([
            {'record_type': 'review',
             'id': 'I1045730e47e9e6ad31fcdfbaefdad77e2f3b2c3e',
             'subject': 'Fix AttributeError in Keypair._add_details()',
             'owner': {'name': 'John Doe',
                       'email': 'john_doe@gmail.com',
                       'username': 'john_doe'},
             'createdOn': 1379404951,
             'module': 'nova', 'branch': 'master'},
            {'record_type': 'bp',
             'id': 'mod:blueprint',
             'self_link': 'http://launchpad.net/blueprint',
             'owner': 'john_doe',
             'date_created': 1234567890}
        ]))

        self.assertRecordsMatch(
            {'record_type': 'review',
             'user_id': 'john_doe',
             'author_name': 'John Doe',
             'author_email': 'john_doe@gmail.com',
             'company_name': '*independent'},
            processed_records[0])

        self.assertRecordsMatch(
            {'record_type': 'bpd',
             'user_id': 'john_doe',
             'author_name': 'John Doe',
             'company_name': '*independent'},
            processed_records[1])

        user = {'seq': 1,
                'user_id': 'john_doe',
                'launchpad_id': 'john_doe',
                'gerrit_id': 'john_doe',
                'user_name': 'John Doe',
                'emails': ['john_doe@gmail.com'],
                'companies': [{'company_name': '*independent', 'end_date': 0}]}
        self.assertEqual(user, user_processor.load_user(
            record_processor_inst.runtime_storage_inst,
            user_id='john_doe'))
        self.assertEqual(user, user_processor.load_user(
            record_processor_inst.runtime_storage_inst,
            email='john_doe@gmail.com'))

    def test_create_member(self):
        member_record = {'member_id': '123456789',
                         'member_name': 'John Doe',
                         'member_uri': 'http://www.openstack.org/community'
                                       '/members/profile/123456789',
                         'date_joined': 'August 01, 2012 ',
                         'company_draft': 'Mirantis'}

        record_processor_inst = self.make_record_processor()
        result_member = next(record_processor_inst._process_member(
            member_record))

        self.assertEqual(result_member['primary_key'], 'member:123456789')
        self.assertEqual(result_member['date'], utils.member_date_to_timestamp(
            'August 01, 2012 '))
        self.assertEqual(result_member['author_name'], 'John Doe')
        self.assertEqual(result_member['company_name'], 'Mirantis')

        result_user = user_processor.load_user(
            record_processor_inst.runtime_storage_inst,
            member_id='123456789')

        self.assertEqual(result_user['user_name'], 'John Doe')
        self.assertEqual(result_user['company_name'], 'Mirantis')
        self.assertEqual(result_user['companies'],
                         [{'company_name': 'Mirantis', 'end_date': 0}])

    def test_update_member(self):
        member_record = {'member_id': '123456789',
                         'member_name': 'John Doe',
                         'member_uri': 'http://www.openstack.org/community'
                                       '/members/profile/123456789',
                         'date_joined': 'August 01, 2012 ',
                         'company_draft': 'Mirantis'}

        record_processor_inst = self.make_record_processor()

        updated_member_record = member_record
        updated_member_record['member_name'] = 'Bill Smith'
        updated_member_record['company_draft'] = 'Rackspace'

        result_member = next(record_processor_inst._process_member(
            updated_member_record))
        self.assertEqual(result_member['author_name'], 'Bill Smith')
        self.assertEqual(result_member['company_name'], 'Rackspace')

        result_user = user_processor.load_user(
            record_processor_inst.runtime_storage_inst,
            member_id='123456789')

        self.assertEqual(result_user['user_name'], 'Bill Smith')
        self.assertEqual(result_user['companies'],
                         [{'company_name': 'Rackspace', 'end_date': 0}])

    def test_process_email_then_review(self):
        # it is expected that the user profile will contain email and
        # gerrit id, while LP id will be None
        record_processor_inst = self.make_record_processor()

        list(record_processor_inst.process([
            {'record_type': 'email',
             'message_id': '<message-id>',
             'author_email': 'john_doe@gmail.com',
             'subject': 'hello, world!',
             'body': 'lorem ipsum',
             'date': 1234567890},
            {'record_type': 'review',
             'id': 'I1045730e47e9e6ad31fcdfbaefdad77e2f3b2c3e',
             'subject': 'Fix AttributeError in Keypair._add_details()',
             'owner': {'name': 'John Doe',
                       'email': 'john_doe@gmail.com',
                       'username': 'john_doe'},
             'createdOn': 1379404951,
             'module': 'nova', 'branch': 'master'}
        ]))

        user = {'seq': 1,
                'user_id': 'john_doe@gmail.com',
                'gerrit_id': 'john_doe',
                'user_name': 'John Doe',
                'emails': ['john_doe@gmail.com'],
                'companies': [{'company_name': '*independent', 'end_date': 0}]}
        self.assertEqual(user, user_processor.load_user(
            record_processor_inst.runtime_storage_inst,
            email='john_doe@gmail.com'))
        self.assertEqual(user, user_processor.load_user(
            record_processor_inst.runtime_storage_inst,
            gerrit_id='john_doe'))

    def test_process_email_then_review_gerrit_id_same_as_launchpad_id(self):
        # it is expected that the user profile will contain email, LP id and
        # gerrit id
        record_processor_inst = self.make_record_processor(
            lp_user_name={'john_doe': {'name': 'john_doe',
                                       'display_name': 'John Doe'}}
        )

        list(record_processor_inst.process([
            {'record_type': 'email',
             'message_id': '<message-id>',
             'author_email': 'john_doe@gmail.com',
             'subject': 'hello, world!',
             'body': 'lorem ipsum',
             'date': 1234567890},
            {'record_type': 'review',
             'id': 'I1045730e47e9e6ad31fcdfbaefdad77e2f3b2c3e',
             'subject': 'Fix AttributeError in Keypair._add_details()',
             'owner': {'name': 'John Doe',
                       'email': 'john_doe@gmail.com',
                       'username': 'john_doe'},
             'createdOn': 1379404951,
             'module': 'nova', 'branch': 'master'}
        ]))

        user = {'seq': 1,
                'user_id': 'john_doe',
                'launchpad_id': 'john_doe',
                'gerrit_id': 'john_doe',
                'user_name': 'John Doe',
                'emails': ['john_doe@gmail.com'],
                'companies': [{'company_name': '*independent', 'end_date': 0}]}
        self.assertEqual(user, user_processor.load_user(
            record_processor_inst.runtime_storage_inst,
            email='john_doe@gmail.com'))
        self.assertEqual(user, user_processor.load_user(
            record_processor_inst.runtime_storage_inst,
            user_id='john_doe'))
        self.assertEqual(user, user_processor.load_user(
            record_processor_inst.runtime_storage_inst,
            gerrit_id='john_doe'))

    def test_process_commit_then_review_with_different_email(self):
        record_processor_inst = self.make_record_processor(
            lp_info={'john_doe@gmail.com':
                     {'name': 'john_doe', 'display_name': 'John Doe'}},
            lp_user_name={'john_doe': {'name': 'john_doe',
                                       'display_name': 'John Doe'}},
            companies=[{'company_name': 'IBM', 'domains': ['ibm.com']}])

        list(record_processor_inst.process([
            {'record_type': 'commit',
             'commit_id': 'de7e8f297c193fb310f22815334a54b9c76a0be1',
             'author_name': 'John Doe', 'author_email': 'john_doe@gmail.com',
             'date': 1234567890, 'lines_added': 25, 'lines_deleted': 9,
             'release_name': 'havana'},
            {'record_type': 'review',
             'id': 'I1045730e47e9e6ad31fcdfbaefdad77e2f3b2c3e',
             'subject': 'Fix AttributeError in Keypair._add_details()',
             'owner': {'name': 'Bill Smith', 'email': 'bill@smith.to',
                       'username': 'bsmith'},
             'createdOn': 1379404951, 'module': 'nova', 'branch': 'master',
             'patchSets': [
                 {'number': '1',
                  'revision': '4d8984e92910c37b7d101c1ae8c8283a2e6f4a76',
                  'ref': 'refs/changes/16/58516/1',
                  'uploader': {'name': 'Bill Smith', 'email': 'bill@smith.to',
                               'username': 'bsmith'},
                  'createdOn': 1385470730,
                  'approvals': [
                      {'type': 'Code-Review', 'description': 'Code Review',
                       'value': '1', 'grantedOn': 1385478464,
                       'by': {'name': 'John Doe', 'email': 'john_doe@ibm.com',
                              'username': 'john_doe'}}]}]}
        ]))
        user = {'seq': 1,
                'user_id': 'john_doe',
                'launchpad_id': 'john_doe',
                'user_name': 'John Doe',
                'emails': ['john_doe@ibm.com', 'john_doe@gmail.com'],
                'companies': [{'company_name': 'IBM', 'end_date': 0}]}
        self.assertUsersMatch(user, user_processor.load_user(
            record_processor_inst.runtime_storage_inst,
            user_id='john_doe'))
        self.assertUsersMatch(user, user_processor.load_user(
            record_processor_inst.runtime_storage_inst,
            email='john_doe@gmail.com'))
        self.assertUsersMatch(user, user_processor.load_user(
            record_processor_inst.runtime_storage_inst,
            email='john_doe@ibm.com'))

    def test_merge_users(self):
        record_processor_inst = self.make_record_processor(
            lp_user_name={
                'john_doe': {'name': 'john_doe', 'display_name': 'John Doe'}
            },
            companies=[{'company_name': 'IBM', 'domains': ['ibm.com']}],
        )
        runtime_storage_inst = record_processor_inst.runtime_storage_inst

        runtime_storage_inst.set_records(record_processor_inst.process([
            {'record_type': 'bp',
             'id': 'mod:blueprint',
             'self_link': 'http://launchpad.net/blueprint',
             'owner': 'john_doe',
             'date_created': 1234567890},
            {'record_type': 'email',
             'message_id': '<message-id>',
             'author_email': 'john_doe@ibm.com', 'author_name': 'John Doe',
             'subject': 'hello, world!',
             'body': 'lorem ipsum',
             'date': 1234567890},
            {'record_type': 'review',
             'id': 'I1045730e47e9e6ad31fcdfbaefdad77e2f3b2c3e',
             'subject': 'Fix AttributeError in Keypair._add_details()',
             'owner': {'name': 'John Doe',
                       'email': 'john_doe@ibm.com',
                       'username': 'john_doe'},
             'createdOn': 1379404951,
             'module': 'nova', 'branch': 'master'}
        ]))

        record_processor_inst.post_processing({})

        user = {'seq': 2,
                'user_id': 'john_doe',
                'launchpad_id': 'john_doe',
                'gerrit_id': 'john_doe',
                'user_name': 'John Doe',
                'emails': ['john_doe@ibm.com'],
                'companies': [{'company_name': 'IBM', 'end_date': 0}]}
        runtime_storage_inst = record_processor_inst.runtime_storage_inst
        self.assertEqual(2, runtime_storage_inst.get_by_key('user:count'))
        self.assertIsNone(user_processor.load_user(
            runtime_storage_inst, 1))
        self.assertEqual(user, user_processor.load_user(
            runtime_storage_inst, 2))
        self.assertEqual(user, user_processor.load_user(
            runtime_storage_inst, user_id='john_doe'))
        self.assertEqual(user, user_processor.load_user(
            runtime_storage_inst, email='john_doe@ibm.com'))
        self.assertEqual(user, user_processor.load_user(
            runtime_storage_inst, gerrit_id='john_doe'))

        # all records should have the same user_id and company name
        for record in runtime_storage_inst.get_all_records():
            self.assertEqual('john_doe', record['user_id'],
                             message='Record %s' % record['primary_key'])
            self.assertEqual('IBM', record['company_name'],
                             message='Record %s' % record['primary_key'])

    def test_core_user_guess(self):
        record_processor_inst = self.make_record_processor(
            lp_user_name={
                'john_doe': {'name': 'john_doe', 'display_name': 'John Doe'},
                'homer': {'name': 'homer', 'display_name': 'Homer Simpson'},
            },
            companies=[{'company_name': 'IBM', 'domains': ['ibm.com']}],
        )
        runtime_storage_inst = record_processor_inst.runtime_storage_inst

        timestamp = int(time.time())
        runtime_storage_inst.set_records(record_processor_inst.process([
            {'record_type': 'review',
             'id': 'I1045730e47e9e6ad31fcdfbaefdad77e2f3b2c3e',
             'subject': 'Fix AttributeError in Keypair._add_details()',
             'owner': {'name': 'John Doe',
                       'email': 'john_doe@ibm.com',
                       'username': 'john_doe'},
             'createdOn': timestamp,
             'module': 'nova',
             'branch': 'master',
             'patchSets': [
                 {'number': '1',
                  'revision': '4d8984e92910c37b7d101c1ae8c8283a2e6f4a76',
                  'ref': 'refs/changes/16/58516/1',
                  'uploader': {
                      'name': 'Bill Smith',
                      'email': 'bill@smith.to',
                      'username': 'bsmith'},
                  'createdOn': timestamp,
                  'approvals': [
                      {'type': 'Code-Review', 'description': 'Code Review',
                       'value': '2', 'grantedOn': timestamp,
                       'by': {
                           'name': 'John Doe',
                           'email': 'john_doe@ibm.com',
                           'username': 'john_doe'}},
                      {'type': 'Code-Review', 'description': 'Code Review',
                       'value': '-1', 'grantedOn': timestamp - 1,  # differ
                       'by': {
                           'name': 'Homer Simpson',
                           'email': 'hsimpson@gmail.com',
                           'username': 'homer'}}
                  ]
                  }]}
        ]))

        record_processor_inst.post_processing({})

        user_1 = {'seq': 1, 'user_id': 'john_doe',
                  'launchpad_id': 'john_doe', 'user_name': 'John Doe',
                  'emails': ['john_doe@ibm.com'],
                  'core': [('nova', 'master')],
                  'companies': [{'company_name': 'IBM', 'end_date': 0}]}
        user_2 = {'seq': 3, 'user_id': 'homer',
                  'launchpad_id': 'homer', 'user_name': 'Homer Simpson',
                  'emails': ['hsimpson@gmail.com'],
                  'companies': [{'company_name': '*independent',
                                 'end_date': 0}]}
        runtime_storage_inst = record_processor_inst.runtime_storage_inst
        self.assertUsersMatch(user_1, user_processor.load_user(
            runtime_storage_inst, user_id='john_doe'))
        self.assertUsersMatch(user_2, user_processor.load_user(
            runtime_storage_inst, user_id='homer'))

    def test_process_commit_with_coauthors(self):
        record_processor_inst = self.make_record_processor(
            lp_info={'jimi.hendrix@openstack.com':
                     {'name': 'jimi', 'display_name': 'Jimi Hendrix'},
                     'tupac.shakur@openstack.com':
                     {'name': 'tupac', 'display_name': 'Tupac Shakur'},
                     'bob.dylan@openstack.com':
                     {'name': 'bob', 'display_name': 'Bob Dylan'}})
        processed_commits = list(record_processor_inst.process([
            {'record_type': 'commit',
             'commit_id': 'de7e8f297c193fb310f22815334a54b9c76a0be1',
             'author_name': 'Jimi Hendrix',
             'author_email': 'jimi.hendrix@openstack.com', 'date': 1234567890,
             'lines_added': 25, 'lines_deleted': 9, 'release_name': 'havana',
             'coauthor': [{'author_name': 'Tupac Shakur',
                           'author_email': 'tupac.shakur@openstack.com'},
                          {'author_name': 'Bob Dylan',
                           'author_email': 'bob.dylan@openstack.com'}]}]))

        self.assertEqual(3, len(processed_commits))

        self.assertRecordsMatch({
            'user_id': 'tupac',
            'author_email': 'tupac.shakur@openstack.com',
            'author_name': 'Tupac Shakur',
        }, processed_commits[0])
        self.assertRecordsMatch({
            'user_id': 'jimi',
            'author_email': 'jimi.hendrix@openstack.com',
            'author_name': 'Jimi Hendrix',
        }, processed_commits[2])
        self.assertEqual('tupac',
                         processed_commits[0]['coauthor'][0]['user_id'])
        self.assertEqual('bob',
                         processed_commits[0]['coauthor'][1]['user_id'])
        self.assertEqual('jimi',
                         processed_commits[0]['coauthor'][2]['user_id'])

    def test_process_commit_with_coauthors_no_dup_of_author(self):
        record_processor_inst = self.make_record_processor(
            lp_info={'jimi.hendrix@openstack.com':
                     {'name': 'jimi', 'display_name': 'Jimi Hendrix'},
                     'bob.dylan@openstack.com':
                     {'name': 'bob', 'display_name': 'Bob Dylan'}})
        processed_commits = list(record_processor_inst.process([
            {'record_type': 'commit',
             'commit_id': 'de7e8f297c193fb310f22815334a54b9c76a0be1',
             'author_name': 'Jimi Hendrix',
             'author_email': 'jimi.hendrix@openstack.com', 'date': 1234567890,
             'lines_added': 25, 'lines_deleted': 9, 'release_name': 'havana',
             'coauthor': [{'author_name': 'Jimi Hendrix',
                           'author_email': 'jimi.hendrix@openstack.com'},
                          {'author_name': 'Bob Dylan',
                           'author_email': 'bob.dylan@openstack.com'}]}]))

        self.assertEqual(2, len(processed_commits))

        self.assertEqual('jimi',
                         processed_commits[0]['coauthor'][0]['user_id'])
        self.assertEqual('bob',
                         processed_commits[0]['coauthor'][1]['user_id'])

    # record post-processing

    def test_blueprint_mention_count(self):
        record_processor_inst = self.make_record_processor()
        runtime_storage_inst = record_processor_inst.runtime_storage_inst

        runtime_storage_inst.set_records(record_processor_inst.process([
            {'record_type': 'bp',
             'id': 'mod:blueprint',
             'self_link': 'http://launchpad.net/blueprint',
             'owner': 'john_doe',
             'date_created': 1234567890},
            {'record_type': 'bp',
             'id': 'mod:ignored',
             'self_link': 'http://launchpad.net/ignored',
             'owner': 'john_doe',
             'date_created': 1234567890},
            {'record_type': 'email',
             'message_id': '<message-id>',
             'author_email': 'john_doe@gmail.com', 'author_name': 'John Doe',
             'subject': 'hello, world!',
             'body': 'lorem ipsum',
             'date': 1234567890,
             'blueprint_id': ['mod:blueprint']},
            {'record_type': 'email',
             'message_id': '<another-message-id>',
             'author_email': 'john_doe@gmail.com', 'author_name': 'John Doe',
             'subject': 'hello, world!',
             'body': 'lorem ipsum',
             'date': 1234567895,
             'blueprint_id': ['mod:blueprint', 'mod:invalid']},
        ]))
        record_processor_inst.post_processing({})

        bp1 = runtime_storage_inst.get_by_primary_key('bpd:mod:blueprint')
        self.assertEqual(2, bp1['mention_count'])
        self.assertEqual(1234567895, bp1['mention_date'])

        bp2 = runtime_storage_inst.get_by_primary_key('bpd:mod:ignored')
        self.assertEqual(0, bp2['mention_count'])
        self.assertEqual(0, bp2['mention_date'])

        email = runtime_storage_inst.get_by_primary_key('<another-message-id>')
        self.assertIn('mod:blueprint', email['blueprint_id'])
        self.assertNotIn('mod:invalid', email['blueprint_id'])

    def test_mark_disagreement(self):
        record_processor_inst = self.make_record_processor(
            users=[
                {'user_id': 'john_doe',
                 'launchpad_id': 'john_doe',
                 'user_name': 'John Doe',
                 'emails': ['john_doe@ibm.com'],
                 'core': [('nova', 'master')],
                 'companies': [{'company_name': 'IBM', 'end_date': 0}]}
            ],
        )
        timestamp = int(time.time())
        runtime_storage_inst = record_processor_inst.runtime_storage_inst
        runtime_storage_inst.set_records(record_processor_inst.process([
            {'record_type': 'review',
             'id': 'I1045730e47e9e6ad31fcdfbaefdad77e2f3b2c3e',
             'subject': 'Fix AttributeError in Keypair._add_details()',
             'owner': {'name': 'John Doe',
                       'email': 'john_doe@ibm.com',
                       'username': 'john_doe'},
             'createdOn': timestamp,
             'module': 'nova',
             'branch': 'master',
             'status': 'NEW',
             'patchSets': [
                 {'number': '1',
                  'revision': '4d8984e92910c37b7d101c1ae8c8283a2e6f4a76',
                  'ref': 'refs/changes/16/58516/1',
                  'uploader': {
                      'name': 'Bill Smith',
                      'email': 'bill@smith.to',
                      'username': 'bsmith'},
                  'createdOn': timestamp,
                  'approvals': [
                      {'type': 'Code-Review', 'description': 'Code Review',
                       'value': '2', 'grantedOn': timestamp - 1,
                       'by': {
                           'name': 'Homer Simpson',
                           'email': 'hsimpson@gmail.com',
                           'username': 'homer'}},
                      {'type': 'Code-Review', 'description': 'Code Review',
                       'value': '-2', 'grantedOn': timestamp,
                       'by': {
                           'name': 'John Doe',
                           'email': 'john_doe@ibm.com',
                           'username': 'john_doe'}}
                  ]
                  },
                 {'number': '2',
                  'revision': '4d8984e92910c37b7d101c1ae8c8283a2e6f4a76',
                  'ref': 'refs/changes/16/58516/1',
                  'uploader': {
                      'name': 'Bill Smith',
                      'email': 'bill@smith.to',
                      'username': 'bsmith'},
                  'createdOn': timestamp + 1,
                  'approvals': [
                      {'type': 'Code-Review', 'description': 'Code Review',
                       'value': '1', 'grantedOn': timestamp + 2,
                       'by': {
                           'name': 'Homer Simpson',
                           'email': 'hsimpson@gmail.com',
                           'username': 'homer'}},
                      {'type': 'Code-Review', 'description': 'Code Review',
                       'value': '-1', 'grantedOn': timestamp + 3,
                       'by': {
                           'name': 'Bart Simpson',
                           'email': 'bsimpson@gmail.com',
                           'username': 'bart'}},
                      {'type': 'Code-Review', 'description': 'Code Review',
                       'value': '2', 'grantedOn': timestamp + 4,
                       'by': {
                           'name': 'John Doe',
                           'email': 'john_doe@ibm.com',
                           'username': 'john_doe'}}
                  ]
                  }
             ]}
        ]))
        record_processor_inst.post_processing({})

        marks = list([r for r in runtime_storage_inst.get_all_records()
                      if r['record_type'] == 'mark'])

        homer_mark = next(six.moves.filter(
            lambda x: x['date'] == (timestamp - 1), marks), None)
        self.assertTrue(homer_mark.get('disagreement'),
                        msg='Disagreement: core set -2 after +2')

        homer_mark = next(six.moves.filter(
            lambda x: x['date'] == (timestamp + 2), marks), None)
        self.assertFalse(homer_mark.get('disagreement'),
                         msg='No disagreement: core set +2 after +1')

        bart_mark = next(six.moves.filter(
            lambda x: x['date'] == (timestamp + 3), marks), None)
        self.assertTrue(bart_mark.get('disagreement'),
                        msg='Disagreement: core set +2 after -1')

    def test_commit_merge_date(self):
        record_processor_inst = self.make_record_processor()
        runtime_storage_inst = record_processor_inst.runtime_storage_inst

        runtime_storage_inst.set_records(record_processor_inst.process([
            {'record_type': 'commit',
             'commit_id': 'de7e8f2',
             'change_id': ['I104573'],
             'author_name': 'John Doe',
             'author_email': 'john_doe@gmail.com',
             'date': 1234567890,
             'lines_added': 25,
             'lines_deleted': 9,
             'module': u'stackalytics',
             'release_name': 'havana'},
            {'record_type': 'review',
             'id': 'I104573',
             'subject': 'Fix AttributeError in Keypair._add_details()',
             'owner': {'name': 'John Doe',
                       'email': 'john_doe@gmail.com',
                       'username': 'john_doe'},
             'createdOn': 1385478465,
             'lastUpdated': 1385490000,
             'status': 'MERGED',
             'module': 'nova', 'branch': 'master'},
        ]))
        record_processor_inst.post_processing({})

        commit = runtime_storage_inst.get_by_primary_key('de7e8f2')
        self.assertEqual(1385490000, commit['date'])

    def test_commit_module_alias(self):
        record_processor_inst = self.make_record_processor()
        runtime_storage_inst = record_processor_inst.runtime_storage_inst

        with mock.patch('stackalytics.processor.utils.load_repos') as patch:
            patch.return_value = [{'module': 'sahara', 'aliases': ['savanna']}]
            runtime_storage_inst.set_records(record_processor_inst.process([
                {'record_type': 'commit',
                 'commit_id': 'de7e8f2',
                 'change_id': ['I104573'],
                 'author_name': 'John Doe',
                 'author_email': 'john_doe@gmail.com',
                 'date': 1234567890,
                 'lines_added': 25,
                 'lines_deleted': 9,
                 'module': u'savanna',
                 'release_name': 'havana'},
                {'record_type': 'review',
                 'id': 'I104573',
                 'subject': 'Fix AttributeError in Keypair._add_details()',
                 'owner': {'name': 'John Doe',
                           'email': 'john_doe@gmail.com',
                           'username': 'john_doe'},
                 'createdOn': 1385478465,
                 'lastUpdated': 1385490000,
                 'status': 'MERGED',
                 'module': 'nova', 'branch': 'master'},
            ]))
            record_processor_inst.post_processing({})

        commit = runtime_storage_inst.get_by_primary_key('de7e8f2')
        self.assertEqual('sahara', commit['module'])

    # update records

    def _generate_record_commit(self):
        yield {'commit_id': u'0afdc64bfd041b03943ceda7849c4443940b6053',
               'lines_added': 9,
               'module': u'stackalytics',
               'record_type': 'commit',
               'message': u'Closes bug 1212953\n\nChange-Id: '
                          u'I33f0f37b6460dc494abf2520dc109c9893ace9e6\n',
               'subject': u'Fixed affiliation of Edgar and Sumit',
               'loc': 10,
               'user_id': u'john_doe',
               'primary_key': u'0afdc64bfd041b03943ceda7849c4443940b6053',
               'author_email': u'jdoe@super.no',
               'company_name': u'SuperCompany',
               'record_id': 6,
               'lines_deleted': 1,
               'week': 2275,
               'blueprint_id': None,
               'bug_id': u'1212953',
               'files_changed': 1,
               'author_name': u'John Doe',
               'date': 1376737923,
               'launchpad_id': u'john_doe',
               'branches': set([u'master']),
               'change_id': u'I33f0f37b6460dc494abf2520dc109c9893ace9e6',
               'release': u'havana'}

    # mail processing

    def test_process_mail(self):
        record_processor_inst = self.make_record_processor(
            users=[
                {
                    'user_id': 'john_doe',
                    'launchpad_id': 'john_doe',
                    'user_name': 'John Doe',
                    'emails': ['johndoe@gmail.com', 'johndoe@nec.co.jp'],
                    'companies': [
                        {'company_name': 'NEC', 'end_date': 0},
                    ]
                }
            ],
            repos=[{"module": "stackalytics"}]
        )

        processed_commit = list(record_processor_inst.process(
            generate_emails(
                author_email='johndoe@gmail.com',
                author_name='John Doe',
                subject='[openstack-dev] [Stackalytics] Configuration files')
        ))[0]

        expected_commit = {
            'user_id': 'john_doe',
            'author_email': 'johndoe@gmail.com',
            'author_name': 'John Doe',
            'company_name': 'NEC',
            'module': 'stackalytics',
        }

        self.assertRecordsMatch(expected_commit, processed_commit)

    def test_process_mail_guessed(self):
        record_processor_inst = self.make_record_processor(
            users=[
                {
                    'user_id': 'john_doe',
                    'launchpad_id': 'john_doe',
                    'user_name': 'John Doe',
                    'emails': ['johndoe@gmail.com', 'johndoe@nec.co.jp'],
                    'companies': [
                        {'company_name': 'NEC', 'end_date': 0},
                    ]
                }
            ],
            repos=[{'module': 'nova'}, {'module': 'neutron'}]
        )

        processed_commit = list(record_processor_inst.process(
            generate_emails(
                author_email='johndoe@gmail.com',
                author_name='John Doe',
                subject='[openstack-dev] [Neutron] [Nova] Integration issue')
        ))[0]

        expected_commit = {
            'user_id': 'john_doe',
            'author_email': 'johndoe@gmail.com',
            'author_name': 'John Doe',
            'company_name': 'NEC',
            'module': 'neutron',
        }

        self.assertRecordsMatch(expected_commit, processed_commit)

    def test_process_mail_guessed_module_in_body_override(self):
        record_processor_inst = self.make_record_processor(
            users=[
                {
                    'user_id': 'john_doe',
                    'launchpad_id': 'john_doe',
                    'user_name': 'John Doe',
                    'emails': ['johndoe@gmail.com', 'johndoe@nec.co.jp'],
                    'companies': [
                        {'company_name': 'NEC', 'end_date': 0},
                    ]
                }
            ],
            repos=[{'module': 'nova'}, {'module': 'neutron'}]
        )

        processed_commit = list(record_processor_inst.process(
            generate_emails(
                author_email='johndoe@gmail.com',
                author_name='John Doe',
                module='nova',
                subject='[openstack-dev] [neutron] Comments/questions on the')
        ))[0]

        expected_commit = {
            'user_id': 'john_doe',
            'author_email': 'johndoe@gmail.com',
            'author_name': 'John Doe',
            'company_name': 'NEC',
            'module': 'neutron',
        }

        self.assertRecordsMatch(expected_commit, processed_commit)

    def test_process_mail_guessed_module_in_body(self):
        record_processor_inst = self.make_record_processor(
            users=[
                {
                    'user_id': 'john_doe',
                    'launchpad_id': 'john_doe',
                    'user_name': 'John Doe',
                    'emails': ['johndoe@gmail.com', 'johndoe@nec.co.jp'],
                    'companies': [
                        {'company_name': 'NEC', 'end_date': 0},
                    ]
                }
            ],
            repos=[{'module': 'nova'}, {'module': 'neutron'}]
        )

        processed_commit = list(record_processor_inst.process(
            generate_emails(
                author_email='johndoe@gmail.com',
                author_name='John Doe',
                module='nova',
                subject='[openstack-dev] Comments/questions on the')
        ))[0]

        expected_commit = {
            'user_id': 'john_doe',
            'author_email': 'johndoe@gmail.com',
            'author_name': 'John Doe',
            'company_name': 'NEC',
            'module': 'nova',
        }

        self.assertRecordsMatch(expected_commit, processed_commit)

    def test_process_mail_unmatched(self):
        record_processor_inst = self.make_record_processor(
            users=[
                {
                    'user_id': 'john_doe',
                    'launchpad_id': 'john_doe',
                    'user_name': 'John Doe',
                    'emails': ['johndoe@gmail.com', 'johndoe@nec.co.jp'],
                    'companies': [
                        {'company_name': 'NEC', 'end_date': 0},
                    ]
                }
            ],
            repos=[{'module': 'nova'}, {'module': 'neutron'}]
        )

        processed_commit = list(record_processor_inst.process(
            generate_emails(
                author_email='johndoe@gmail.com',
                author_name='John Doe',
                subject='[openstack-dev] Comments/questions on the')
        ))[0]

        expected_commit = {
            'user_id': 'john_doe',
            'author_email': 'johndoe@gmail.com',
            'author_name': 'John Doe',
            'company_name': 'NEC',
            'module': 'unknown',
        }

        self.assertRecordsMatch(expected_commit, processed_commit)

    def test_get_modules(self):
        record_processor_inst = self.make_record_processor()
        with mock.patch('stackalytics.processor.utils.load_repos') as patch:
            patch.return_value = [{'module': 'nova'},
                                  {'module': 'python-novaclient'},
                                  {'module': 'neutron'},
                                  {'module': 'sahara', 'aliases': ['savanna']}]
            modules, module_alias_map = record_processor_inst._get_modules()
            self.assertEqual(set(['nova', 'neutron', 'sahara', 'savanna']),
                             set(modules))
            self.assertEqual({'savanna': 'sahara'}, module_alias_map)

    def test_guess_module(self):
        record_processor_inst = self.make_record_processor()
        with mock.patch('stackalytics.processor.utils.load_repos') as patch:
            patch.return_value = [{'module': 'sahara', 'aliases': ['savanna']}]
            record = {'subject': '[savanna] T'}
            record_processor_inst._guess_module(record)
            self.assertEqual({'subject': '[savanna] T', 'module': 'sahara'},
                             record)

    def assertRecordsMatch(self, expected, actual):
        for key, value in six.iteritems(expected):
            self.assertEqual(value, actual.get(key),
                             'Values for key %s do not match' % key)

    def assertUsersMatch(self, expected, actual):
        self.assertIsNotNone(actual, 'User should not be None')
        match = True
        for key, value in six.iteritems(expected):
            if key == 'emails':
                match = (set(value) == set(actual.get(key)))
            else:
                match = (value == actual.get(key))

        self.assertTrue(match, 'User %s should match %s' % (actual, expected))

    # Helpers

    def make_record_processor(self, users=None, companies=None, releases=None,
                              repos=None, lp_info=None, lp_user_name=None):
        rp = record_processor.RecordProcessor(make_runtime_storage(
            users=users, companies=companies, releases=releases, repos=repos))

        if lp_info is not None:
            self.lp_profile_by_email.side_effect = (
                lambda x: lp_info.get(x))

        if lp_user_name is not None:
            self.lp_profile_by_launchpad_id.side_effect = (
                lambda x: lp_user_name.get(x))

        return rp


def generate_commits(author_name='John Doe', author_email='johndoe@gmail.com',
                     date=1999999999):
    yield {
        'record_type': 'commit',
        'commit_id': 'de7e8f297c193fb310f22815334a54b9c76a0be1',
        'author_name': author_name,
        'author_email': author_email,
        'date': date,
        'lines_added': 25,
        'lines_deleted': 9,
        'release_name': 'havana',
    }


def generate_emails(author_name='John Doe', author_email='johndoe@gmail.com',
                    date=1999999999, subject='[openstack-dev]', module=None):
    yield {
        'record_type': 'email',
        'message_id': 'de7e8f297c193fb310f22815334a54b9c76a0be1',
        'author_name': author_name,
        'author_email': author_email,
        'date': date,
        'subject': subject,
        'module': module,
        'body': 'lorem ipsum',
    }


def make_runtime_storage(users=None, companies=None, releases=None,
                         repos=None):
    runtime_storage_cache = {}
    runtime_storage_record_keys = []

    def get_by_key(key):
        if key == 'companies':
            return _make_companies(companies or [
                {"company_name": "*independent", "domains": [""]},
            ])
        elif key == 'users':
            return _make_users(users or [])
        elif key == 'releases':
            return releases or RELEASES
        elif key == 'repos':
            return repos or REPOS
        else:
            return runtime_storage_cache.get(key)

    def set_by_key(key, value):
        runtime_storage_cache[key] = value

    def delete_by_key(key):
        del runtime_storage_cache[key]

    def inc_user_count():
        count = runtime_storage_cache.get('user:count') or 0
        count += 1
        runtime_storage_cache['user:count'] = count
        return count

    def get_all_users():
        for n in six.moves.range(
                0, (runtime_storage_cache.get('user:count') or 0) + 1):
            u = runtime_storage_cache.get('user:%s' % n)
            if u:
                yield u

    def set_records(records_iterator):
        for record in records_iterator:
            runtime_storage_cache[record['primary_key']] = record
            runtime_storage_record_keys.append(record['primary_key'])

    def get_all_records():
        return [runtime_storage_cache[key]
                for key in runtime_storage_record_keys]

    def get_by_primary_key(primary_key):
        return runtime_storage_cache.get(primary_key)

    rs = mock.Mock(runtime_storage.RuntimeStorage)
    rs.get_by_key = mock.Mock(side_effect=get_by_key)
    rs.set_by_key = mock.Mock(side_effect=set_by_key)
    rs.delete_by_key = mock.Mock(side_effect=delete_by_key)
    rs.inc_user_count = mock.Mock(side_effect=inc_user_count)
    rs.get_all_users = mock.Mock(side_effect=get_all_users)
    rs.set_records = mock.Mock(side_effect=set_records)
    rs.get_all_records = mock.Mock(side_effect=get_all_records)
    rs.get_by_primary_key = mock.Mock(side_effect=get_by_primary_key)

    if users:
        for user in users:
            set_by_key('user:%s' % user['user_id'], user)
            if user.get('launchpad_id'):
                set_by_key('user:%s' % user['launchpad_id'], user)
            for email in user.get('emails') or []:
                set_by_key('user:%s' % email, user)

    return rs


def _make_users(users):
    users_index = {}
    for user in users:
        if 'user_id' in user:
            users_index[user['user_id']] = user
        if 'launchpad_id' in user:
            users_index[user['launchpad_id']] = user
        for email in user['emails']:
            users_index[email] = user
    return users_index


def _make_companies(companies):
    domains_index = {}
    for company in companies:
        for domain in company['domains']:
            domains_index[domain] = company['company_name']
    return domains_index
