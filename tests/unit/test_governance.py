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

from stackalytics.processor import governance


SAMPLE = """
Sahara:
  ptl: Sergey Lukjanov (SergeyLukjanov)
  irc-channel: openstack-sahara
  service: Data processing service
  mission: >
    To provide a scalable data processing stack and associated management
    interfaces.
  url: https://wiki.openstack.org/wiki/Sahara
  deliverables:
    python-saharaclient:
      repos:
        - openstack/python-saharaclient
      tags:
        - release:cycle-with-intermediary
        - release:has-stable-branches
        - type:library
        - release:managed
        - vulnerability:managed
    sahara:
      repos:
        - openstack/sahara
        - openstack/sahara-extra
        - openstack/sahara-image-elements
      tags:
        - tc-approved-release
        - release:managed
        - release:cycle-with-milestones
        - release:has-stable-branches
        - type:service
        - vulnerability:managed
    sahara-dashboard:
      repos:
        - openstack/sahara-dashboard
      tags:
        - type:library
    sahara-specs:
      repos:
        - openstack/sahara-specs
"""


class TestGovernance(testtools.TestCase):

    @mock.patch('stackalytics.processor.utils.read_uri')
    def test_read_official_projects_yaml(self, read_uri):
        read_uri.return_value = SAMPLE

        expected = {
            'sahara-group': {
                'id': 'sahara-group',
                'module_group_name': 'Sahara Official',
                'modules': ['python-saharaclient', 'sahara',
                            'sahara-dashboard', 'sahara-extra',
                            'sahara-image-elements', 'sahara-specs'],
                'tag': 'program'
            },
            'tc-approved-release': {
                'id': 'tc-approved-release',
                'module_group_name': 'tc-approved-release',
                'modules': ['sahara', 'sahara-extra', 'sahara-image-elements'],
                'tag': 'project_type'
            }
        }

        actual = governance.read_projects_yaml('uri')

        self.assertEqual(expected, actual)
