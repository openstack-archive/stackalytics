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

import mock
import testtools

from stackalytics.processor import record_processor
from stackalytics.processor import runtime_storage
from stackalytics.processor import utils


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
        "uri": "git://github.com/stackforge/stackalytics.git"
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
            'lp_profile_by_launchpad_id')
        self.lp_profile_by_launchpad_id = (
            self.lp_profile_by_launchpad_id_patch.start())
        self.lp_profile_by_launchpad_id.return_value = None
        self.lp_profile_by_email_patch = mock.patch(
            'stackalytics.processor.launchpad_utils.lp_profile_by_email')
        self.lp_profile_by_email = (
            self.lp_profile_by_email_patch.start())
        self.lp_profile_by_email.return_value = None

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
        res = record_processor_inst._get_company_by_email(email)
        self.assertEquals('IBM', res)

    def test_get_company_by_email_with_long_suffix_mapped(self):
        record_processor_inst = self.make_record_processor(
            companies=[{'company_name': 'NEC', 'domains': ['nec.co.jp']}]
        )
        email = 'man@mxw.nes.nec.co.jp'
        res = record_processor_inst._get_company_by_email(email)
        self.assertEquals('NEC', res)

    def test_get_company_by_email_with_long_suffix_mapped_2(self):
        record_processor_inst = self.make_record_processor(
            companies=[{'company_name': 'NEC',
                        'domains': ['nec.co.jp', 'nec.com']}]
        )
        email = 'man@mxw.nes.nec.com'
        res = record_processor_inst._get_company_by_email(email)
        self.assertEquals('NEC', res)

    def test_get_company_by_email_not_mapped(self):
        record_processor_inst = self.make_record_processor()
        email = 'foo@boo.com'
        res = record_processor_inst._get_company_by_email(email)
        self.assertEquals(None, res)

    # get_lp_info

    def test_get_lp_info_invalid_email(self):
        self.read_launchpad.return_value = None
        record_processor_inst = self.make_record_processor(users=[])
        self.assertEquals((None, None),
                          record_processor_inst._get_lp_info('error.root'))

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
            'launchpad_id': 'john_doe',
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
            'launchpad_id': 'john_doe',
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
            'launchpad_id': 'john_doe',
            'author_email': 'johndoe@ibm.com',
            'author_name': 'John Doe',
            'company_name': 'IBM',
        }

        self.assertRecordsMatch(expected_commit, processed_commit)
        self.assertIn('johndoe@ibm.com',
                      record_processor_inst.users_index['john_doe']['emails'])

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
            'launchpad_id': 'john_doe',
            'author_email': 'johndoe@gmail.com',
            'author_name': 'John Doe',
            'company_name': 'NEC',
        }

        self.assertRecordsMatch(expected_commit, processed_commit)
        self.assertIn('johndoe@gmail.com',
                      record_processor_inst.users_index['john_doe']['emails'])

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
            'launchpad_id': 'john_doe',
            'author_email': 'johndoe@ibm.com',
            'author_name': 'John Doe',
            'company_name': 'IBM',
        }

        self.assertRecordsMatch(expected_commit, processed_commit)
        user = record_processor_inst.users_index['john_doe']
        self.assertIn('johndoe@gmail.com', user['emails'])
        self.assertEquals('IBM', user['companies'][0]['company_name'],
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
            'launchpad_id': 'john_doe',
            'author_email': 'johndoe@ibm.com',
            'author_name': 'John Doe',
            'company_name': 'IBM',
        }

        self.assertRecordsMatch(expected_commit, processed_commit)
        user = record_processor_inst.users_index['john_doe']
        self.assertIn('johndoe@ibm.com', user['emails'])
        self.assertEquals('IBM', user['companies'][0]['company_name'])

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
        self.assertEquals(1, len(record_processor_inst.users_index))
        user = record_processor_inst.users_index['johndoe@ibm.com']
        self.assertIn('johndoe@ibm.com', user['emails'])
        self.assertEquals('IBM', user['companies'][0]['company_name'])
        self.assertEquals(None, user['launchpad_id'])

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

        self.assertEquals(1, len(record_processor_inst.users_index))
        user = record_processor_inst.users_index['john_doe']
        self.assertEquals({
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

        self.assertEquals(1, len(record_processor_inst.users_index))
        user = record_processor_inst.users_index['john_doe']
        self.assertEquals({
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
             'module': 'nova'}
        ]))

        self.assertRecordsMatch(
            {'record_type': 'bpd',
             'launchpad_id': 'john_doe',
             'author_name': 'John Doe',
             'company_name': '*independent'},
            processed_records[0])

        self.assertRecordsMatch(
            {'record_type': 'review',
             'launchpad_id': 'john_doe',
             'author_name': 'John Doe',
             'author_email': 'john_doe@gmail.com',
             'company_name': '*independent'},
            processed_records[1])

        user = {'user_id': 'john_doe',
                'launchpad_id': 'john_doe',
                'user_name': 'John Doe',
                'emails': ['john_doe@gmail.com'],
                'companies': [{'company_name': '*independent', 'end_date': 0}]}
        self.assertEquals({'john_doe': user, 'john_doe@gmail.com': user},
                          record_processor_inst.users_index)

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
             'launchpad_id': 'john_doe',
             'author_name': 'John Doe',
             'author_email': 'john_doe@gmail.com',
             'company_name': '*independent'},
            processed_records[1])

        user = {'user_id': 'john_doe',
                'launchpad_id': 'john_doe',
                'user_name': 'John Doe',
                'emails': ['john_doe@gmail.com'],
                'companies': [{'company_name': '*independent', 'end_date': 0}]}
        self.assertEquals({'john_doe': user, 'john_doe@gmail.com': user},
                          record_processor_inst.users_index)

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
             'module': 'nova'},
            {'record_type': 'bp',
             'id': 'mod:blueprint',
             'self_link': 'http://launchpad.net/blueprint',
             'owner': 'john_doe',
             'date_created': 1234567890}
        ]))

        self.assertRecordsMatch(
            {'record_type': 'review',
             'launchpad_id': 'john_doe',
             'author_name': 'John Doe',
             'author_email': 'john_doe@gmail.com',
             'company_name': '*independent'},
            processed_records[0])

        self.assertRecordsMatch(
            {'record_type': 'bpd',
             'launchpad_id': 'john_doe',
             'author_name': 'John Doe',
             'company_name': '*independent'},
            processed_records[1])

        user = {'user_id': 'john_doe',
                'launchpad_id': 'john_doe',
                'user_name': 'John Doe',
                'emails': ['john_doe@gmail.com'],
                'companies': [{'company_name': '*independent', 'end_date': 0}]}
        self.assertEquals({'john_doe': user, 'john_doe@gmail.com': user},
                          record_processor_inst.users_index)

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

    def test_update_record_no_changes(self):
        commit_generator = self._generate_record_commit()
        release_index = {'0afdc64bfd041b03943ceda7849c4443940b6053': 'havana'}
        record_processor_inst = self.make_record_processor(
            users=[],
            companies=[{'company_name': 'SuperCompany',
                        'domains': ['super.no']}])

        updated = list(record_processor_inst.update(commit_generator,
                                                    release_index))

        self.assertEquals(0, len(updated))

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
            'launchpad_id': 'john_doe',
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
            'launchpad_id': 'john_doe',
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
            'launchpad_id': 'john_doe',
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
            'launchpad_id': 'john_doe',
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
            'launchpad_id': 'john_doe',
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
                                  {'module': 'neutron'}]
            modules = record_processor_inst._get_modules()
            self.assertEqual(set(['nova', 'neutron']), set(modules))

    def assertRecordsMatch(self, expected, actual):
        for key, value in expected.iteritems():
            self.assertEquals(value, actual[key],
                              'Values for key %s do not match' % key)

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
    def get_by_key(collection):
        if collection == 'companies':
            return _make_companies(companies or [
                {"company_name": "*independent", "domains": [""]},
            ])
        elif collection == 'users':
            return _make_users(users or [])
        elif collection == 'releases':
            return releases or RELEASES
        elif collection == 'repos':
            return repos or REPOS
        else:
            raise Exception('Wrong collection: %s' % collection)

    rs = mock.Mock(runtime_storage.RuntimeStorage)
    rs.get_by_key = mock.Mock(side_effect=get_by_key)
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
