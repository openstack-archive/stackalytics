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

import testtools

from stackalytics.processor import user_processor
from stackalytics.processor import utils


class TestUserProcessor(testtools.TestCase):

    def test_update_user(self):
        user = {
            "launchpad_id": "user",
            "companies": [
                {
                    "company_name": "Rackspace",
                    "end_date": "2011-Nov-20"
                },
                {
                    "company_name": "IBM",
                    "end_date": None
                }
            ],
            "user_name": "John Smith",
            "emails": ["john@smith.com"]
        }

        stored_user = {
            "launchpad_id": "user",
            "companies": [
                {
                    "company_name": "Rackspace",
                    "end_date": "2011-Nov-20"
                },
                {
                    "company_name": "IBM",
                    "end_date": None
                }
            ],
            "user_name": "Johnny",
            "emails": ["john@smith.com", "mapped_email@gmail.com"],
            "static": True
        }

        updated_user = user_processor.update_user_profile(stored_user, user)

        # merge emails from profile with those discovered by Stackalytics
        self.assertEqual(set(stored_user['emails']),
                         set(updated_user['emails']))
        # name from the profile has higher priority over mined
        self.assertEqual(user['user_name'], updated_user['user_name'])
        # static flag must present
        self.assertTrue(updated_user.get('static'))

    def test_update_user_unknown_user(self):
        user = {
            "launchpad_id": "user",
            "companies": [
                {
                    "company_name": "Rackspace",
                    "end_date": "2011-Nov-20"
                },
                {
                    "company_name": "IBM",
                    "end_date": None
                }
            ],
            "user_name": "John Smith",
            "emails": ["john@smith.com"]
        }

        stored_user = None

        updated_user = user_processor.update_user_profile(stored_user, user)
        self.assertTrue(updated_user.get('static'))

    def test_are_users_same(self):
        users = [
            dict(seq=1),
            dict(seq=1),
            dict(seq=1),
        ]
        self.assertTrue(user_processor.are_users_same(users))

    def test_are_users_same_none(self):
        users = [
            {},
            {},
        ]
        self.assertFalse(user_processor.are_users_same(users))

    def test_are_users_not_same(self):
        users = [
            dict(seq=1),
            dict(seq=2),
            dict(seq=1),
        ]
        self.assertFalse(user_processor.are_users_same(users))

    def test_are_users_not_same_2(self):
        users = [
            dict(seq=1),
            dict(seq=1),
            {}
        ]
        self.assertFalse(user_processor.are_users_same(users))

    def test_resolve_companies_aliases(self):
        domains_index = {
            utils.normalize_company_name('IBM India'): 'IBM',
            utils.normalize_company_name('IBM Japan'): 'IBM',
        }
        user = [
            dict(company_name='IBM India', end_date=1234567890),
            dict(company_name='IBM Japan', end_date=2234567890),
            dict(company_name='Intel', end_date=0),
        ]

        observed = user_processor.resolve_companies_aliases(
            domains_index, user)

        expected = [
            dict(company_name='IBM', end_date=2234567890),
            dict(company_name='Intel', end_date=0),
        ]
        self.assertEqual(expected, observed)
