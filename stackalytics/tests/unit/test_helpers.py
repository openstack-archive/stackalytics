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

import mock
import testtools

from stackalytics.dashboard import helpers


class TestHelpers(testtools.TestCase):

    @mock.patch('time.time')
    def test_get_current_company(self, mock_time_time):
        current_timestamp = 1234567890
        mock_time_time.return_value = current_timestamp

        user = {
            'user_id': 'smith',
            'user_name': 'John Smith',
            'companies': [{
                'company_name': 'Current',
                'end_date': current_timestamp + 1
            }, {
                'company_name': 'TheCompany',
                'end_date': 0
            }]
        }

        self.assertEqual('Current', helpers.get_current_company(user))

    @mock.patch('stackalytics.dashboard.helpers.make_link')
    def test_extend_user(self, mock_make_link):
        company_link = mock.Mock()
        mock_make_link.return_value = company_link

        user = {
            'user_id': 'smith',
            'user_name': 'John Smith',
            'companies': [{
                'company_name': 'TheCompany',
                'end_date': 0
            }]
        }

        expected = {
            'user_id': 'smith',
            'user_name': 'John Smith',
            'companies': [{
                'company_name': 'TheCompany',
                'end_date': 0
            }],
            'id': 'smith',
            'company_link': company_link,
            'text': 'John Smith',
        }

        observed = helpers.extend_user(user)
        self.assertEqual(expected, observed)
        mock_make_link.assert_called_once_with('TheCompany', '/', mock.ANY)

    @mock.patch('time.time')
    @mock.patch('stackalytics.dashboard.helpers.make_link')
    def test_extend_user_current_company(self, mock_make_link, mock_time_time):
        company_link = mock.Mock()
        mock_make_link.return_value = company_link
        current_timestamp = 1234567890
        mock_time_time.return_value = current_timestamp

        user = {
            'user_id': 'smith',
            'user_name': 'John Smith',
            'companies': [{
                'company_name': 'Current',
                'end_date': current_timestamp + 1
            }, {
                'company_name': 'TheCompany',
                'end_date': 0
            }]
        }

        helpers.extend_user(user)

        mock_make_link.assert_called_once_with('Current', '/', mock.ANY)
