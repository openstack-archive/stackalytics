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

import json
import mock
import testtools

from stackalytics.processor import bps


BUG = json.loads("""
{
    "date_closed": "2015-06-02T17:31:05.820479+00:00",
    "date_assigned": "2015-06-02T17:31:44.957976+00:00",
    "title": "Bug #1458945 in Sahara: \\\"Use graduated oslo.policy\\\"",
    "bug_link": "https://api.launchpad.net/devel/bugs/1458945",
    "bug_watch_link": null,
    "milestone_link": null,
    "date_left_closed": null,
    "date_fix_committed": "2015-06-02T17:31:05.820479+00:00",
    "date_fix_released": "2015-06-02T17:31:05.820479+00:00",
    "date_in_progress": "2015-06-02T17:31:05.820479+00:00",
    "resource_type_link": "https://api.launchpad.net/devel/#bug_task",
    "status": "Fix Released",
    "bug_target_name": "sahara",
    "importance": "Medium",
    "assignee_link": "https://api.launchpad.net/devel/~slukjanov",
    "date_triaged": "2015-06-02T17:31:05.820479+00:00",
    "self_link": "https://api.launchpad.net/devel/sahara/+bug/1458945",
    "target_link": "https://api.launchpad.net/devel/sahara",
    "bug_target_display_name": "Sahara",
    "related_tasks_collection_link":
      "https://api.launchpad.net/devel/sahara/+bug/1458945/related_tasks",
    "date_confirmed": "2015-06-02T17:31:05.820479+00:00",
    "date_left_new": "2015-06-02T17:31:05.820479+00:00",
    "web_link": "https://bugs.launchpad.net/sahara/+bug/1458945",
    "owner_link": "https://api.launchpad.net/devel/~samueldmq",
    "date_created": "2015-06-02T13:35:54.101235+00:00",
    "date_incomplete": null,
    "is_complete": true
}
""")

ANOTHER_MILESTONE_BUG = json.loads("""
{
    "date_closed": "2015-06-02T17:31:05.820479+00:00",
    "date_assigned": "2015-06-02T17:31:44.957976+00:00",
    "title": "Bug #1458945 in Sahara Kilo: \\\"Use graduated oslo.policy\\\"",
    "bug_link": "https://api.launchpad.net/devel/bugs/1458945",
    "bug_watch_link": null,
    "milestone_link": null,
    "date_left_closed": null,
    "date_fix_committed": "2015-06-02T17:31:05.820479+00:00",
    "date_fix_released": "2015-06-02T17:31:05.820479+00:00",
    "date_in_progress": "2015-06-02T17:31:05.820479+00:00",
    "resource_type_link": "https://api.launchpad.net/devel/#bug_task",
    "status": "Fix Released",
    "bug_target_name": "sahara/kilo",
    "importance": "Medium",
    "assignee_link": "https://api.launchpad.net/devel/~slukjanov",
    "date_triaged": "2015-06-02T17:31:05.820479+00:00",
    "self_link": "https://api.launchpad.net/devel/sahara/kilo/+bug/1458945",
    "target_link": "https://api.launchpad.net/devel/sahara/kilo",
    "bug_target_display_name": "Sahara Kilo",
    "related_tasks_collection_link":
      "https://api.launchpad.net/devel/sahara/kilo/+bug/1458945/related_tasks",
    "date_confirmed": "2015-06-02T17:31:05.820479+00:00",
    "date_left_new": "2015-06-02T17:31:05.820479+00:00",
    "web_link": "https://bugs.launchpad.net/sahara/kilo/+bug/1458945",
    "owner_link": "https://api.launchpad.net/devel/~samueldmq",
    "date_created": "2015-06-02T13:35:54.101235+00:00",
    "date_incomplete": null,
    "is_complete": true
}
""")

LINKED_BUG = json.loads("""
{
    "date_closed": "2015-06-24T20:59:57.982386+00:00",
    "date_assigned": "2015-06-18T06:46:03.741208+00:00",
    "title": "Bug #1458945 in Barbican: \\\"Use graduated oslo.policy\\\"",
    "bug_link": "https://api.launchpad.net/devel/bugs/1458945",
    "bug_watch_link": null,
    "milestone_link":
      "https://api.launchpad.net/devel/barbican/+milestone/liberty-1",
    "date_left_closed": null,
    "date_fix_committed": "2015-06-18T06:45:39.997949+00:00",
    "date_fix_released": "2015-06-24T20:59:57.982386+00:00",
    "date_in_progress": "2015-06-18T06:45:39.997949+00:00",
    "resource_type_link": "https://api.launchpad.net/devel/#bug_task",
    "status": "Fix Released",
    "bug_target_name": "barbican",
    "importance": "Medium",
    "assignee_link": "https://api.launchpad.net/devel/~juan-osorio-robles",
    "date_triaged": "2015-06-18T06:45:39.997949+00:00",
    "self_link": "https://api.launchpad.net/devel/barbican/+bug/1458945",
    "target_link": "https://api.launchpad.net/devel/barbican",
    "bug_target_display_name": "Barbican",
    "related_tasks_collection_link":
      "https://api.launchpad.net/devel/barbican/+bug/1458945/related_tasks",
    "date_confirmed": "2015-06-18T06:45:39.997949+00:00",
    "date_left_new": "2015-06-18T06:45:39.997949+00:00",
    "web_link": "https://bugs.launchpad.net/barbican/+bug/1458945",
    "owner_link": "https://api.launchpad.net/devel/~samueldmq",
    "date_created": "2015-05-26T17:47:32.438795+00:00",
    "date_incomplete": null,
    "is_complete": true
}
""")

RELEASED_NOT_COMMITTED_BUG = json.loads("""
{
    "date_closed": "2015-06-02T17:31:05.820479+00:00",
    "date_assigned": "2015-06-02T17:31:44.957976+00:00",
    "title": "Bug #1458945 in Sahara: \\\"Use graduated oslo.policy\\\"",
    "bug_link": "https://api.launchpad.net/devel/bugs/1458945",
    "bug_watch_link": null,
    "milestone_link": null,
    "date_left_closed": null,
    "date_fix_committed": null,
    "date_fix_released": "2015-06-02T17:31:05.820479+00:00",
    "date_in_progress": "2015-06-02T17:31:05.820479+00:00",
    "resource_type_link": "https://api.launchpad.net/devel/#bug_task",
    "status": "Fix Released",
    "bug_target_name": "sahara",
    "importance": "Medium",
    "assignee_link": "https://api.launchpad.net/devel/~slukjanov",
    "date_triaged": "2015-06-02T17:31:05.820479+00:00",
    "self_link": "https://api.launchpad.net/devel/sahara/+bug/1458945",
    "target_link": "https://api.launchpad.net/devel/sahara",
    "bug_target_display_name": "Sahara",
    "related_tasks_collection_link":
      "https://api.launchpad.net/devel/sahara/+bug/1458945/related_tasks",
    "date_confirmed": "2015-06-02T17:31:05.820479+00:00",
    "date_left_new": "2015-06-02T17:31:05.820479+00:00",
    "web_link": "https://bugs.launchpad.net/sahara/+bug/1458945",
    "owner_link": "https://api.launchpad.net/devel/~samueldmq",
    "date_created": "2015-06-02T13:35:54.101235+00:00",
    "date_incomplete": null,
    "is_complete": true
}
""")


class TestBps(testtools.TestCase):
    def setUp(self):
        super(TestBps, self).setUp()
        p_module_exists = mock.patch(
            'stackalytics.processor.launchpad_utils.lp_module_exists')
        m_module_exists = p_module_exists.start()
        m_module_exists.return_value = True

    @mock.patch('stackalytics.processor.launchpad_utils.lp_bug_generator')
    def test_log(self, lp_bug_generator):
        repo = {
            'module': 'sahara'
        }
        modified_since = 1234567890
        lp_bug_generator.return_value = iter([BUG])

        expected = [{
            'assignee': 'slukjanov',
            'date_created': 1433252154,
            'date_fix_committed': 1433266265,
            'date_fix_released': 1433266265,
            'id': 'sahara/1458945',
            'importance': 'Medium',
            'module': 'sahara',
            'owner': 'samueldmq',
            'status': 'Fix Released',
            'title': 'Bug #1458945 in Sahara: "Use graduated oslo.policy"',
            'web_link': 'https://bugs.launchpad.net/sahara/+bug/1458945'
        }]

        actual = list(bps.log(repo, modified_since))

        self.assertEqual(expected, actual)

    @mock.patch('stackalytics.processor.launchpad_utils.lp_bug_generator')
    def test_log_released_not_committed(self, lp_bug_generator):
        repo = {
            'module': 'sahara'
        }
        modified_since = 1234567890
        lp_bug_generator.return_value = iter([RELEASED_NOT_COMMITTED_BUG])

        expected = [{
            'assignee': 'slukjanov',
            'date_created': 1433252154,
            'date_fix_released': 1433266265,
            'id': 'sahara/1458945',
            'importance': 'Medium',
            'module': 'sahara',
            'owner': 'samueldmq',
            'status': 'Fix Released',
            'title': 'Bug #1458945 in Sahara: "Use graduated oslo.policy"',
            'web_link': 'https://bugs.launchpad.net/sahara/+bug/1458945'
        }]

        actual = list(bps.log(repo, modified_since))

        self.assertEqual(expected, actual)

    @mock.patch('stackalytics.processor.launchpad_utils.lp_bug_generator')
    def test_log_additional_module(self, lp_bug_generator):
        # bug linked to another project should not appear
        repo = {
            'module': 'sahara'
        }
        modified_since = 1234567890
        lp_bug_generator.return_value = iter([BUG, LINKED_BUG])

        expected = [{
            'assignee': 'slukjanov',
            'date_created': 1433252154,
            'date_fix_committed': 1433266265,
            'date_fix_released': 1433266265,
            'id': 'sahara/1458945',
            'importance': 'Medium',
            'module': 'sahara',
            'owner': 'samueldmq',
            'status': 'Fix Released',
            'title': 'Bug #1458945 in Sahara: "Use graduated oslo.policy"',
            'web_link': 'https://bugs.launchpad.net/sahara/+bug/1458945'
        }]

        actual = list(bps.log(repo, modified_since))

        self.assertEqual(expected, actual)

    @mock.patch('stackalytics.processor.launchpad_utils.lp_bug_generator')
    def test_log_additional_milestone(self, lp_bug_generator):
        # bug linked to different milestone should be mapped to the release
        repo = {
            'module': 'sahara'
        }
        modified_since = 1234567890
        lp_bug_generator.return_value = iter([BUG, ANOTHER_MILESTONE_BUG])

        expected = [{
            'assignee': 'slukjanov',
            'date_created': 1433252154,
            'date_fix_committed': 1433266265,
            'date_fix_released': 1433266265,
            'id': 'sahara/1458945',
            'importance': 'Medium',
            'module': 'sahara',
            'owner': 'samueldmq',
            'status': 'Fix Released',
            'title': 'Bug #1458945 in Sahara: "Use graduated oslo.policy"',
            'web_link': 'https://bugs.launchpad.net/sahara/+bug/1458945'
        }, {
            'assignee': 'slukjanov',
            'date_created': 1433252154,
            'date_fix_committed': 1433266265,
            'date_fix_released': 1433266265,
            'id': 'sahara/kilo/1458945',
            'importance': 'Medium',
            'module': 'sahara',
            'release': 'kilo',
            'owner': 'samueldmq',
            'status': 'Fix Released',
            'title': 'Bug #1458945 in Sahara Kilo: '
                     '"Use graduated oslo.policy"',
            'web_link': 'https://bugs.launchpad.net/sahara/kilo/+bug/1458945'

        }]

        actual = list(bps.log(repo, modified_since))

        self.assertEqual(expected, actual)

    @mock.patch('stackalytics.processor.launchpad_utils.lp_module_exists')
    @mock.patch('stackalytics.processor.launchpad_utils.lp_bug_generator')
    def test_log_module_alias(self, lp_bug_generator, lp_module_exists):
        # bug linked to another project should not appear
        repo = {
            'module': 'savanna',
            'aliases': ['sahara']
        }
        modified_since = 1234567890
        lp_bug_generator.return_value = iter([BUG])
        lp_module_exists.side_effect = iter([False, True])

        expected = [{
            'assignee': 'slukjanov',
            'date_created': 1433252154,
            'date_fix_committed': 1433266265,
            'date_fix_released': 1433266265,
            'id': 'savanna/1458945',
            'importance': 'Medium',
            'module': 'savanna',  # should be the same as primary module name
            'owner': 'samueldmq',
            'status': 'Fix Released',
            'title': 'Bug #1458945 in Sahara: "Use graduated oslo.policy"',
            'web_link': 'https://bugs.launchpad.net/sahara/+bug/1458945'
        }]

        actual = list(bps.log(repo, modified_since))

        self.assertEqual(expected, actual)
