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

import testtools

from stackalytics.processor import mps


class TestMps(testtools.TestCase):

    def test_member_parse_regex(self):

        content = '''<h1>Individual Member Profile</h1>
<div class="candidate span-14">
<div class="span-4">
<img src="/themes/openstack/images/generic-profile-photo.png"><p>&nbsp;</p>
</div>
<a name="profile-10501"></a>
<div class="details span-10 last">
<div class="last name-and-title">
<h3>Jim Battenberg</h3>
</div>
<hr><div class="span-4"><strong>Date Joined</strong></div>
<div class="span-6 last">June 25, 2013 <br><br></div>
    <div class="span-4"><strong>Affiliations</strong></div>
    <div class="span-6 last">
            <div>
                <b>Rackspace</b> From  (Current)
            </div>
    </div>
<div class="span-4"><strong>Statement of Interest </strong></div>
<div class="span-6 last">
<p>contribute logic and evangelize openstack</p>
</div>
<p>&nbsp;</p>'''

        match = re.search(mps.NAME_AND_DATE_PATTERN, content)
        self.assertTrue(match)
        self.assertEqual('Jim Battenberg', match.group('member_name'))
        self.assertEqual('June 25, 2013 ', match.group('date_joined'))

        match = re.search(mps.COMPANY_PATTERN, content)
        self.assertTrue(match)
        self.assertEqual('Rackspace', match.group('company_draft'))
