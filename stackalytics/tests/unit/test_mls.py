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

import re

import mock
import testtools

from stackalytics.processor import mls


EMAIL_CONTENT = '''
From sorlando at nicira.com  Tue Jul 17 07:30:43 2012
From: sorlando at nicira.com (Salvatore Orlando)
Date: Tue, 17 Jul 2012 00:30:43 -0700
Subject: [openstack-dev] [nova] [pci device passthrough] fails with
 "NameError: global name '_' is not defined"
In-Reply-To: <5004FBF1.1080102@redhat.com>
References: <5004FBF1.1080102@redhat.com>
Message-ID: <CAGR=i3htLvDOdh5u6mxqmo0zVP1eKKYAxAhj=e1-rpQWZOiF6Q@gmail.com>

Good morning Gary!
-----------------

test works :)

> Reply
'''


class TestMls(testtools.TestCase):

    def test_mail_parse_regex(self):

        content = '''
URL: <http://lists.openstack.org/pipermail/openstack-dev/>

From sorlando at nicira.com  Tue Jul 17 07:30:43 2012
From: sorlando at nicira.com (Salvatore Orlando)
Date: Tue, 17 Jul 2012 00:30:43 -0700
Subject: [openstack-dev] [nova] [pci device passthrough] fails with
 "NameError: global name '_' is not defined"
In-Reply-To: <5004FBF1.1080102@redhat.com>
References: <5004FBF1.1080102@redhat.com>
Message-ID: <CAGR=i3htLvDOdh5u6mxqmo0zVP1eKKYAxAhj=e1-rpQWZOiF6Q@gmail.com>

Good morning Gary!

test works :)

From sorlando at nicira.com  Tue Jul 17 07:30:43 2012
From: sorlando at nicira.com (Salvatore Orlando)
            '''
        match = re.search(mls.MAIL_BOX_PATTERN, content)
        self.assertTrue(match)
        self.assertEqual('sorlando at nicira.com', match.group(1))
        self.assertEqual('Salvatore Orlando', match.group(2))
        self.assertEqual('Tue, 17 Jul 2012 00:30:43 -0700', match.group(3))
        self.assertEqual('[openstack-dev] [nova] [pci device passthrough] '
                         'fails with\n "NameError: global name \'_\' is not '
                         'defined"', match.group(4))
        self.assertEqual('<CAGR=i3htLvDOdh5u6mxqmo0zVP1eKKYAxAhj='
                         'e1-rpQWZOiF6Q@gmail.com>', match.group(5))
        self.assertEqual('Good morning Gary!\n\ntest works :)\n',
                         match.group(6))

    @mock.patch('stackalytics.processor.utils.read_gzip_from_uri')
    @mock.patch('stackalytics.processor.mls._get_mail_archive_links')
    @mock.patch('stackalytics.processor.mls._uri_content_changed')
    def test_log(self, mock_uri_content_changed, mock_get_mail_archive_links,
                 mock_read_gzip_from_uri):
        mock_uri_content_changed.return_value = True
        mock_get_mail_archive_links.return_value = ['link']
        mock_read_gzip_from_uri.return_value = EMAIL_CONTENT
        mock_rsi = mock.Mock()

        emails = list(mls.log('uri', mock_rsi))

        self.assertEqual(1, len(emails))
        self.assertEqual('Good morning Gary!\n\ntest works :)\n',
                         emails[0]['body'])
