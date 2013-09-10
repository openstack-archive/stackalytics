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

from stackalytics.processor import utils


class TestUtils(testtools.TestCase):
    def setUp(self):
        super(TestUtils, self).setUp()

    def _test_one_range(self, start, end, step):
        elements = set()
        for chunk in utils.make_range(start, end, step):
            for item in chunk:
                self.assertFalse(item in elements)
                elements.add(item)

        self.assertTrue(set(range(start, end)) == elements)

    def test_make_range_0_10_1(self):
        self._test_one_range(0, 10, 1)

    def test_make_range_0_10_3(self):
        self._test_one_range(0, 10, 3)

    def test_make_range_3_5_4(self):
        self._test_one_range(3, 5, 4)

    def test_make_range_5_26_10(self):
        self._test_one_range(5, 26, 10)
