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

import contextlib
import mock
import testtools

from dashboard import web
from stackalytics.processor import runtime_storage


class TestAPI(testtools.TestCase):

    def setUp(self):
        super(TestAPI, self).setUp()
        self.app = web.app.test_client()


@contextlib.contextmanager
def make_runtime_storage(data):
    def get_by_key(key):
        return data.get(key)

    def get_update(pid):
        return []

    setattr(web.app, 'stackalytics_vault', None)
    runtime_storage_inst = mock.Mock(runtime_storage.RuntimeStorage)
    runtime_storage_inst.get_by_key = get_by_key
    runtime_storage_inst.get_update = get_update

    with mock.patch('stackalytics.processor.runtime_storage.'
                    'get_runtime_storage') as get_runtime_storage_mock:
        get_runtime_storage_mock.return_value = runtime_storage_inst
        try:
            yield runtime_storage_inst
        finally:
            pass
