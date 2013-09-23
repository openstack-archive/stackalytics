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

from dashboard import web


class TestWebUtils(testtools.TestCase):
    def setUp(self):
        super(TestWebUtils, self).setUp()

    def test_make_commit_message(self):
        message = '''
During finish_migration the manager calls initialize_connection but doesn't
update the block_device_mapping with the potentially new connection_info
returned.


Fixes bug 1076801
Change-Id: Ie49ccd2138905e178843b375a9b16c3fe572d1db'''

        module = 'test'

        record = {
            'message': message,
            'module': module,
        }

        expected = '''\
During finish_migration the manager calls initialize_connection but doesn't \
update the block_device_mapping with the potentially new connection_info \
returned.
Fixes bug <a href="https://bugs.launchpad.net/bugs/1076801" class="ext_link">\
1076801</a>
''' + ('Change-Id: <a href="https://review.openstack.org/#q,'
       'Ie49ccd2138905e178843b375a9b16c3fe572d1db,n,z" class="ext_link">'
       'Ie49ccd2138905e178843b375a9b16c3fe572d1db</a>')

        observed = web.make_commit_message(record)

        self.assertEqual(expected, observed,
                         'Commit message should be processed correctly')

    def test_make_commit_message_blueprint_link(self):
        message = '''
Implemented new driver for Cinder <:
Implements Blueprint super-driver
Change-Id: Ie49ccd2138905e178843b375a9b16c3fe572d1db'''

        module = 'cinder'

        record = {
            'message': message,
            'module': module,
        }

        expected = '''\
Implemented new driver for Cinder &lt;:
Implements Blueprint ''' + (
            '<a href="https://blueprints.launchpad.net/cinder/+spec/'
            'super-driver" class="ext_link">super-driver</a>' + '\n' +
            'Change-Id: <a href="https://review.openstack.org/#q,'
            'Ie49ccd2138905e178843b375a9b16c3fe572d1db,n,z" class="ext_link">'
            'Ie49ccd2138905e178843b375a9b16c3fe572d1db</a>')

        observed = web.make_commit_message(record)

        self.assertEqual(expected, observed,
                         'Commit message should be processed correctly')

    def test_unwrap(self):
        original = 'Lorem ipsum. Dolor\nsit amet.\n Lorem\n ipsum.\ndolor!\n'
        expected = 'Lorem ipsum. Dolor sit amet.\n Lorem\n ipsum.\ndolor!'

        self.assertEqual(expected, web.unwrap_text(original))

    def test_unwrap_split_long_link(self):
        original = ('https://blueprints.launchpad.net/stackalytics/+spec/'
                    'stackalytics-core')
        expected = ('https://&#8203;blueprints.launchpad.net/&#8203;'
                    'stackalytics/&#8203;+spec/&#8203;stackalytics-core')

        self.assertEqual(expected, web.make_commit_message(
            {'message': original, 'module': 'none'}))

    @mock.patch('dashboard.web.get_vault')
    @mock.patch('dashboard.web.get_user_from_runtime_storage')
    def test_make_page_title(self, user_patch, vault_patch):
        memory_storage_mock = mock.Mock()
        memory_storage_mock.get_original_company_name = mock.Mock(
            return_value='Mirantis'
        )
        vault_patch.return_value = {'memory_storage': memory_storage_mock}
        user_patch.return_value = {'user_name': 'John Doe'}

        self.assertEqual('OpenStack community contribution in all releases',
                         web.make_page_title('', '', '', 'all'))
        self.assertEqual('OpenStack community contribution in Havana release',
                         web.make_page_title('', '', '', 'Havana'))
        self.assertEqual('Mirantis contribution in Havana release',
                         web.make_page_title('Mirantis', '', '', 'Havana'))
        self.assertEqual('John Doe contribution in Havana release',
                         web.make_page_title('', 'john_doe', '', 'Havana'))
        self.assertEqual(
            'John Doe (Mirantis) contribution to neutron in Havana release',
            web.make_page_title('Mirantis', 'John Doe', 'neutron', 'Havana'))
