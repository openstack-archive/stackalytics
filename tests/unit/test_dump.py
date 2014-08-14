# Copyright (c) 2014 Mirantis Inc.
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

import memcache
import mock
import testtools

from stackalytics.processor import dump


class TestDump(testtools.TestCase):

    def _make_data(self, record_count):
        data = {'record:count': record_count}
        for i in range(record_count):
            data['record:%d' % i] = i
        return data

    def test_export_data_records(self):
        record_count = 153
        data = self._make_data(record_count)
        memcache_inst = mock.Mock(memcache.Client)
        memcache_inst.get = lambda x: data.get(x)
        memcache_inst.get_multi = lambda keys, key_prefix: dict(
            ('%s' % n, data.get(key_prefix + '%s' % n)) for n in keys)

        with mock.patch('pickle.dump') as pickle_dump:
            fd = mock.Mock()
            dump.export_data(memcache_inst, fd)
            # self.assertEquals(total, pickle_dump.call_count)

            expected_calls = [mock.call(('record:count', record_count), fd)]
            for i in range(record_count):
                expected_calls.append(mock.call(('record:%d' % i,
                                                 data['record:%d' % i]), fd))
            pickle_dump.assert_has_calls(expected_calls, any_order=True)

    def test_export_data_records_get_multi_truncates_chunk(self):
        record_count = 153
        data = self._make_data(record_count)
        memcache_inst = mock.Mock(memcache.Client)
        memcache_inst.get = lambda x: data.get(x)
        memcache_inst.get_multi = lambda keys, key_prefix: dict(
            ('%s' % n, data.get(key_prefix + '%s' % n))
            for n in [k for k, v in zip(keys, range(len(keys) - 1))])

        with mock.patch('pickle.dump') as pickle_dump:
            fd = mock.Mock()
            dump.export_data(memcache_inst, fd)
            # self.assertEquals(total, pickle_dump.call_count)

            expected_calls = [mock.call(('record:count', record_count), fd)]
            for i in range(record_count):
                expected_calls.append(mock.call(('record:%d' % i,
                                                 data['record:%d' % i]), fd))
            pickle_dump.assert_has_calls(expected_calls, any_order=True)
