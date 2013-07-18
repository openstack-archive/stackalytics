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

        expected = '''
During finish_migration the manager calls initialize_connection but doesn't
update the block_device_mapping with the potentially new connection_info
returned.
Fixes bug <a href="https://bugs.launchpad.net/bugs/1076801">1076801</a>
''' + ('Change-Id: <a href="https://review.openstack.org/#q,'
       'Ie49ccd2138905e178843b375a9b16c3fe572d1db,n,z">'
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

        expected = '''
Implemented new driver for Cinder &lt;:
Implements Blueprint ''' + (
            '<a href="https://blueprints.launchpad.net/cinder/+spec/'
            'super-driver">super-driver</a>' + '\n' +
            'Change-Id: <a href="https://review.openstack.org/#q,'
            'Ie49ccd2138905e178843b375a9b16c3fe572d1db,n,z">'
            'Ie49ccd2138905e178843b375a9b16c3fe572d1db</a>')

        observed = web.make_commit_message(record)

        self.assertEqual(expected, observed,
                         'Commit message should be processed correctly')
