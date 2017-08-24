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

from stackalytics.processor import launchpad_utils


class TestLaunchpadUtils(testtools.TestCase):

    @mock.patch('stackalytics.processor.launchpad_utils._lp_profile_by_email')
    def test_get_lp_info(self, lp_mock):
        lp_mock.return_value = dict(name='john', display_name='smith')

        observed = launchpad_utils.query_lp_info('john@smith.to')

        self.assertEqual(('john', 'smith'), observed)
        lp_mock.assert_called_once_with('john@smith.to')

    @mock.patch('stackalytics.processor.launchpad_utils._lp_profile_by_email')
    def test_get_lp_info_not_found(self, lp_mock):
        lp_mock.return_value = None

        observed = launchpad_utils.query_lp_info('john@smith.to')

        self.assertEqual((None, None), observed)
        lp_mock.assert_called_once_with('john@smith.to')

    @mock.patch('stackalytics.processor.launchpad_utils._lp_profile_by_email')
    def test_get_lp_info_invalid_email(self, lp_mock):

        observed = launchpad_utils.query_lp_info('error.root')

        self.assertEqual((None, None), observed)
        lp_mock.assert_not_called()
