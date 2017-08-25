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

from stackalytics.processor import openstackid_utils as ou

USER_PROFILE = {
    "total": 1,
    "data": [
        {
            "id": 5555,
            "first_name": "John",
            "last_name": "Smith",
            "affiliations": [
                {
                    "start_date": 1193875200,
                    "end_date": 1496188800,
                    "organization": {
                        "name": "Mirantis"
                    }
                },
                {
                    "start_date": 1496275200,
                    "end_date": None,
                    "organization": {
                        "name": "Huawei"
                    }
                }
            ]
        }
    ]
}
USER_PROFILE_NO_AFFILIATIONS = {
    "total": 1,
    "data": [
        {
            "id": 5555,
            "first_name": "John",
            "last_name": "Smith",
            "affiliations": []
        }
    ]
}
USER_PROFILE_NO_DATES = {
    "total": 1,
    "data": [
        {
            "id": 2222,
            "first_name": "John",
            "last_name": "Smith",
            "affiliations": [
                {
                    "start_date": None,
                    "end_date": None,
                    "is_current": True,
                    "organization": {
                        "name": "Hewlett Packard Enterprise"
                    }
                }
            ]
        }
    ]
}
USER_PROFILE_MULTIPLE_RECORDS = {
    "total": 1,
    "data": [
        {
            "id": 2222,
            "first_name": "John",
            "last_name": "Smith",
            "affiliations": [
                {
                    "start_date": None,
                    "end_date": None,
                    "is_current": True,
                    "organization": {
                        "name": "Hewlett Packard Enterprise"
                    }
                }
            ]
        },
        {
            "id": 5555,
            "first_name": "John",
            "last_name": "Smith",
            "affiliations": [
                {
                    "start_date": 1456790400,
                    "end_date": None,
                    "organization": {
                        "name": "Red Hat"
                    }
                }
            ]
        }
    ]
}
USER_PROFILE_NO_CURRENT = {
    "total": 1,
    "data": [
        {
            "id": 5555,
            "first_name": "John",
            "last_name": "Smith",
            "affiliations": [
                {
                    "start_date": 1193875200,
                    "end_date": 1496188800,
                    "organization": {
                        "name": "Mirantis"
                    }
                }
            ]
        }
    ]
}
USER_PROFILE_MULTIPLE_CURRENT = {
    "total": 1,
    "data": [
        {
            "id": 1111,
            "first_name": "John",
            "last_name": "Smith",
            "affiliations": [
                {
                    "start_date": 1378339200,
                    "end_date": None,
                    "is_current": True,
                    "organization": {
                        "name": "NTT"
                    }
                },
                {
                    "start_date": 1442880000,
                    "end_date": None,
                    "is_current": True,
                    "organization": {
                        "name": "NTT DATA"
                    }
                }
            ]
        }
    ]
}


class TestOpenStackIDUtils(testtools.TestCase):

    def test_iterate_intervals(self):
        origin = [ou.Interval(100, 200, 'a'),
                  ou.Interval(200, 0, 'b')]
        expected = [ou.Interval(0, 100, None),
                    ou.Interval(100, 200, 'a'),
                    ou.Interval(200, 0, 'b')]

        observed = list(ou._iterate_intervals(origin, threshold=10))
        self.assertEqual(expected, observed)

    def test_iterate_intervals_2(self):
        origin = [ou.Interval(100, 200, 'a'),
                  ou.Interval(300, 400, 'b')]
        expected = [ou.Interval(0, 100, None),
                    ou.Interval(100, 200, 'a'),
                    ou.Interval(200, 300, None),
                    ou.Interval(300, 400, 'b'),
                    ou.Interval(400, 0, None)]

        observed = list(ou._iterate_intervals(origin, threshold=10))
        self.assertEqual(expected, observed)

    @mock.patch('stackalytics.processor.utils.read_json_from_uri')
    def test_user_profile_by_email(self, reader_mock):
        reader_mock.return_value = USER_PROFILE
        email = 'dummy@dummy.org'

        expected = {
            'openstack_id': 5555,
            'user_name': 'John Smith',
            'emails': [email],
            'companies': [{
                'company_name': '*independent',
                'end_date': 1193875200
            }, {
                'company_name': 'Mirantis',
                'end_date': 1496188800
            }, {
                'company_name': 'Huawei',
                'end_date': 0
            }]
        }

        observed = ou.user_profile_by_email(email)

        reader_mock.assert_called_once_with(
            ou.OSID_URI % email, session=ou._openstackid_session)
        self.assertEqual(expected, observed)

    @mock.patch('stackalytics.processor.utils.read_json_from_uri')
    def test_user_profile_by_email_not_affiliated(self, reader_mock):
        reader_mock.return_value = USER_PROFILE_NO_AFFILIATIONS
        email = 'dummy@dummy.org'

        expected = {
            'openstack_id': 5555,
            'user_name': 'John Smith',
            'emails': [email],
            'companies': [{
                'company_name': '*independent',
                'end_date': 0
            }]
        }

        observed = ou.user_profile_by_email(email)

        reader_mock.assert_called_once_with(
            ou.OSID_URI % email, session=ou._openstackid_session)
        self.assertEqual(expected, observed)

    @mock.patch('stackalytics.processor.utils.read_json_from_uri')
    def test_user_profile_by_email_not_found(self, reader_mock):
        reader_mock.return_value = {
            "total": 0,
            "data": []
        }
        email = 'dummy@dummy.org'

        expected = None
        observed = ou.user_profile_by_email(email)

        reader_mock.assert_called_once_with(
            ou.OSID_URI % email, session=ou._openstackid_session)
        self.assertEqual(expected, observed)

    @mock.patch('stackalytics.processor.utils.read_json_from_uri')
    def test_user_profile_by_email_not_read(self, reader_mock):
        reader_mock.return_value = None
        email = 'dummy@dummy.org'

        expected = None
        observed = ou.user_profile_by_email(email)

        reader_mock.assert_called_once_with(
            ou.OSID_URI % email, session=ou._openstackid_session)
        self.assertEqual(expected, observed)

    @mock.patch('stackalytics.processor.utils.read_json_from_uri')
    def test_user_profile_by_email_no_dates(self, reader_mock):
        reader_mock.return_value = USER_PROFILE_NO_DATES
        email = 'dummy@dummy.org'

        expected = {
            'openstack_id': 2222,
            'user_name': 'John Smith',
            'emails': [email],
            'companies': [{
                'company_name': 'Hewlett Packard Enterprise',
                'end_date': 0
            }]
        }

        observed = ou.user_profile_by_email(email)

        reader_mock.assert_called_once_with(
            ou.OSID_URI % email, session=ou._openstackid_session)
        self.assertEqual(expected, observed)

    @mock.patch('stackalytics.processor.utils.read_json_from_uri')
    def test_user_profile_by_email_multiple_records(self, reader_mock):
        reader_mock.return_value = USER_PROFILE_MULTIPLE_RECORDS
        email = 'dummy@dummy.org'

        expected = {
            'openstack_id': 5555,
            'user_name': 'John Smith',
            'emails': [email],
            'companies': [{
                'company_name': '*independent',
                'end_date': 1456790400
            }, {
                'company_name': 'Red Hat',
                'end_date': 0
            }]
        }

        observed = ou.user_profile_by_email(email)

        reader_mock.assert_called_once_with(
            ou.OSID_URI % email, session=ou._openstackid_session)
        self.assertEqual(expected, observed)

    @mock.patch('stackalytics.processor.utils.read_json_from_uri')
    def test_user_profile_by_email_no_current(self, reader_mock):
        reader_mock.return_value = USER_PROFILE_NO_CURRENT
        email = 'dummy@dummy.org'

        expected = {
            'openstack_id': 5555,
            'user_name': 'John Smith',
            'emails': [email],
            'companies': [{
                'company_name': '*independent',
                'end_date': 1193875200
            }, {
                'company_name': 'Mirantis',
                'end_date': 1496188800
            }, {
                'company_name': '*independent',
                'end_date': 0
            }]
        }

        observed = ou.user_profile_by_email(email)

        reader_mock.assert_called_once_with(
            ou.OSID_URI % email, session=ou._openstackid_session)
        self.assertEqual(expected, observed)

    @mock.patch('stackalytics.processor.utils.read_json_from_uri')
    def test_user_profile_by_email_multiple_current(self, reader_mock):
        reader_mock.return_value = USER_PROFILE_MULTIPLE_CURRENT
        email = 'dummy@dummy.org'

        expected = {
            'openstack_id': 1111,
            'user_name': 'John Smith',
            'emails': [email],
            'companies': [{
                'company_name': '*independent',
                'end_date': 1378339200
            }, {
                'company_name': 'NTT',
                'end_date': 1442880000
            }, {
                'company_name': 'NTT DATA',
                'end_date': 0
            }]
        }

        observed = ou.user_profile_by_email(email)

        reader_mock.assert_called_once_with(
            ou.OSID_URI % email, session=ou._openstackid_session)
        self.assertEqual(expected, observed)
