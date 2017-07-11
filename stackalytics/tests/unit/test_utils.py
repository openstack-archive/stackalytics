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

from stackalytics.processor import utils


class TestUtils(testtools.TestCase):

    def _test_one_range(self, start, end, step):
        elements = set()
        for chunk in utils.make_range(start, end, step):
            for item in chunk:
                self.assertNotIn(item, elements)
                elements.add(item)

        self.assertSetEqual(set(range(start, end)), elements)

    def test_make_range_0_10_1(self):
        self._test_one_range(0, 10, 1)

    def test_make_range_0_10_3(self):
        self._test_one_range(0, 10, 3)

    def test_make_range_3_5_4(self):
        self._test_one_range(3, 5, 4)

    def test_make_range_5_26_10(self):
        self._test_one_range(5, 26, 10)

    def test_email_valid(self):
        self.assertTrue(utils.check_email_validity('pupkin@gmail.com'))
        self.assertTrue(utils.check_email_validity('v.pup_kin2@ntt.co.jp'))

    def test_email_invalid(self):
        self.assertFalse(utils.check_email_validity('pupkin@localhost'))
        self.assertFalse(utils.check_email_validity('222@some.(trash)'))

    def test_unwrap(self):
        original = 'Lorem ipsum. Dolor\nsit amet.\n Lorem\n ipsum.\ndolor!\n'
        expected = 'Lorem ipsum. Dolor sit amet.\n Lorem\n ipsum.\ndolor!'

        self.assertEqual(expected, utils.unwrap_text(original))

    def test_format_text_split_long_link(self):
        original = ('https://blueprints.launchpad.net/stackalytics/+spec/'
                    'stackalytics-core')
        expected = ('https://blueprints.&#8203;launchpad.&#8203;net'
                    '/&#8203;stackalytics/+spec/&#8203;stackalytics-core')

        self.assertEqual(expected, utils.format_text(original))

    def test_format_text_split_full_class_path(self):
        original = 'tests.unit.benchmark.scenarios.test_base'
        expected = ('tests.&#8203;unit.&#8203;benchmark.&#8203;'
                    'scenarios.&#8203;test_base')

        self.assertEqual(expected, utils.format_text(original))

    def test_format_text_split_full_class_path_middle_line(self):
        original = 'some text tests.unit.benchmark.scenarios.test_base wide'
        expected = ('some text tests.&#8203;unit.&#8203;benchmark.&#8203;'
                    'scenarios.&#8203;test_base wide')

        self.assertEqual(expected, utils.format_text(original))

    def test_add_index(self):
        sequence = [{'name': 'A'}, {'name': 'B'}, {'name': 'C'}]
        expected = [{'index': 1, 'name': 'A'}, {'index': 2, 'name': 'B'},
                    {'index': 3, 'name': 'C'}]
        self.assertEqual(expected, utils.add_index(sequence))

    def test_add_index_with_filter(self):
        sequence = [{'name': 'A'}, {'name': 'B'}, {'name': 'C'}]
        expected = [{'index': 0, 'name': 'A'}, {'index': '', 'name': 'B'},
                    {'index': 1, 'name': 'C'}]
        self.assertEqual(expected, utils.add_index(
            sequence, start=0, item_filter=lambda x: x['name'] != 'B'))

    def test_keep_safe_chars(self):
        self.assertEqual('somemoretext',
                         utils.keep_safe_chars('some more text'))
        self.assertEqual(u'(unicode)',
                         utils.keep_safe_chars(u'(unicode \u0423) '))

    def test_normalize_company_name(self):
        company_names = ['EMC Corporation', 'Abc, corp..', 'Mirantis IT.',
                         'Red Hat, Inc.', 'abc s.r.o. ABC', '2s.r.o. co',
                         'AL.P.B L.P. s.r.o. s.r.o. C ltd.']
        correct_normalized_company_names = ['emc', 'abc', 'mirantis',
                                            'redhat', 'abcabc', '2sro',
                                            'alpbc']
        normalized_company_names = [utils.normalize_company_name(name)
                                    for name in company_names]

        self.assertEqual(normalized_company_names,
                         correct_normalized_company_names)

    def test_validate_lp_display_name(self):
        profile = dict(name='johnny', display_name='John Smith')
        utils.validate_lp_display_name(profile)
        self.assertEqual('John Smith', profile['display_name'])

        profile = dict(name='johnny', display_name='<email address hidden>')
        utils.validate_lp_display_name(profile)
        self.assertEqual('johnny', profile['display_name'])

        profile = None
        utils.validate_lp_display_name(profile)
        self.assertIsNone(profile)

    def test_pipeline_processor(self):
        counter = dict(n=0)
        consumed = []
        log = mock.Mock()

        def get_all_items():
            for i in range(5):
                counter['n'] += 1
                yield i

        def single_pass_uno():
            log('single_pass_uno:begin')

            def pass_1(s):
                yield s

            yield pass_1

            log('single_pass_uno:end')

        def single_pass_duo():
            log('single_pass_duo:begin')

            def pass_1(s):
                yield s + 10

            yield pass_1

            log('single_pass_duo:end')

        def double_pass():
            log('double_pass:begin')
            r = set()

            def pass_1(s):
                if s % 2:
                    r.add(s)

            yield pass_1

            log('double_pass:middle')

            def pass_2(s):
                if s in r:
                    yield s * 100

            yield pass_2

            log('double_pass:end')

        def consume(r):
            for x in r:
                consumed.append(x)

        processors = [single_pass_uno, double_pass, single_pass_duo]
        pipeline_processor = utils.make_pipeline_processor(processors)
        consume(pipeline_processor(get_all_items))

        self.assertEqual(10, counter['n'])  # twice by 5 elements

        expected = [0, 10, 1, 11, 2, 12, 3, 13, 4, 14, 100, 300]
        self.assertEqual(expected, consumed)

        log.assert_has_calls([
            mock.call('single_pass_uno:begin'),
            mock.call('double_pass:begin'),
            mock.call('single_pass_duo:begin'),
            mock.call('single_pass_uno:end'),
            mock.call('double_pass:middle'),
            mock.call('single_pass_duo:end'),
            mock.call('double_pass:end'),
        ])
