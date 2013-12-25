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
import itertools
import mock
import testtools
import uuid

from dashboard import web
from stackalytics.processor import runtime_storage


class TestAPI(testtools.TestCase):

    def setUp(self):
        super(TestAPI, self).setUp()
        self.app = web.app.test_client()


@contextlib.contextmanager
def make_runtime_storage(data, *generators):
    _add_generated_records(data, *generators)

    runtime_storage_inst = TestStorage(data)
    setattr(web.app, 'stackalytics_vault', None)

    with mock.patch('stackalytics.processor.runtime_storage.'
                    'get_runtime_storage') as get_runtime_storage_mock:
        get_runtime_storage_mock.return_value = runtime_storage_inst
        try:
            yield runtime_storage_inst
        finally:
            pass


def make_records(**kwargs):
    def generate_records():
        record_types = kwargs.get('record_type', [])
        if 'commit' in record_types:
            for commit in _generate_commits(algebraic_product(**kwargs)):
                yield commit
        elif 'mark' in record_types:
            for mark in _generate_marks(algebraic_product(**kwargs)):
                yield mark

    return generate_records


class TestStorage(runtime_storage.RuntimeStorage):

    def __init__(self, data):
        super(TestStorage, self).__init__('test://')
        self.data = data

    def get_update(self, pid):
        for record in self.get_all_records():
            yield record

    def get_by_key(self, key):
        return self.data.get(key)

    def set_by_key(self, key, value):
        super(TestStorage, self).set_by_key(key, value)

    def get_all_records(self):
        for n in range(self.get_by_key('record:count') or 0):
            record = self.get_by_key('record:%s' % n)
            if record:
                yield record


def _generate_commits(values_list):
    for values in values_list:
        commit = {
            'commit_id': str(uuid.uuid4()),
            'lines_added': 9, 'module': 'nova', 'record_type': 'commit',
            'message': 'Closes bug 1212953\n\nChange-Id: '
                       'I33f0f37b6460dc494abf2520dc109c9893ace9e6\n',
            'subject': 'Fixed affiliation of Edgar and Sumit', 'loc': 10,
            'user_id': 'john_doe',
            'primary_key': str(uuid.uuid4()),
            'author_email': 'john_doe@ibm.com', 'company_name': 'IBM',
            'lines_deleted': 1, 'week': 2275,
            'blueprint_id': None, 'bug_id': u'1212953',
            'files_changed': 1, 'author_name': u'John Doe',
            'date': 1376737923, 'launchpad_id': u'john_doe',
            'branches': set([u'master']),
            'change_id': u'I33f0f37b6460dc494abf2520dc109c9893ace9e6',
            'release': u'icehouse'
        }
        commit.update(values)
        yield commit


def _generate_marks(values_list):
    for values in values_list:
        mark = {
            'record_type': 'mark',
            'id': str(uuid.uuid4()),
            'module': 'nova',
            'message': str(uuid.uuid4()),
            'subject': 'Fixed affiliation of Edgar and Sumit',
            'user_id': 'john_doe',
            'primary_key': str(uuid.uuid4()),
            'author_email': 'john_doe@ibm.com', 'company_name': 'IBM',
            'week': 2275,
            'blueprint_id': None, 'bug_id': '1212953',
            'author_name': 'John Doe',
            'date': 1376737923, 'launchpad_id': 'john_doe',
            'branches': set(['master']),
            'change_id': 'I33f0f37b6460dc494abf2520dc109c9893ace9e6',
            'release': 'icehouse'
        }
        mark.update(values)
        yield mark


def _add_generated_records(data, *generators):
    count = 0
    for gen in generators:
        for record in gen():
            record['record_id'] = count
            data['record:%s' % count] = record
            count += 1
    data['record:count'] = count


def algebraic_product(**kwargs):
    position_to_key = {}
    values = []
    for key, value in kwargs.iteritems():
        position_to_key[len(values)] = key
        values.append(value)

    for chain in itertools.product(*values):
        result = {}
        for position, key in position_to_key.iteritems():
            result[key] = chain[position]
        yield result
