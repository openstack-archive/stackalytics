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
import json

import mock
from oslo_utils import uuidutils
import six
import testtools

from stackalytics.dashboard import web
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
    GENERATORS = {
        'commit': _generate_commits,
        'mark': _generate_marks,
        'review': _generate_review,
    }

    def generate_records():
        for record_type in kwargs.get('record_type', []):
            if record_type in GENERATORS.keys():
                for values in algebraic_product(**kwargs):
                    record = next(GENERATORS[record_type]())
                    record.update(values)
                    yield record

    return generate_records


def make_module(module_name):
    return {'id': module_name,
            'module_group_name': module_name,
            'modules': [module_name],
            'tag': 'module'}


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


def _generate_commits():
        commit = {
            'commit_id': uuidutils.generate_uuid(),
            'lines_added': 9, 'module': 'nova', 'record_type': 'commit',
            'message': 'Closes bug 1212953\n\nChange-Id: '
                       'I33f0f37b6460dc494abf2520dc109c9893ace9e6\n',
            'subject': 'Fixed affiliation of Edgar and Sumit', 'loc': 10,
            'user_id': 'john_doe',
            'primary_key': uuidutils.generate_uuid(),
            'author_email': 'john_doe@ibm.com', 'company_name': 'IBM',
            'lines_deleted': 1, 'week': 2275,
            'blueprint_id': None, 'bug_id': u'1212953',
            'files_changed': 1, 'author_name': u'John Doe',
            'date': 1376737923, 'launchpad_id': u'john_doe',
            'branches': set([u'master']),
            'change_id': u'I33f0f37b6460dc494abf2520dc109c9893ace9e6',
            'release': u'icehouse'
        }
        yield commit


def _generate_marks():
        mark = {
            'launchpad_id': 'john_doe', 'week': 2294, 'user_id': 'john_doe',
            'description': 'Approved', 'author_name': 'John Doe',
            'author_email': 'john_doe@gmail.com',
            'primary_key': uuidutils.generate_uuid() + 'Workflow',
            'module': 'glance', 'patch': 2, 'record_type': 'mark',
            'company_name': '*independent', 'branch': 'master',
            'date': 1387860458, 'record_id': 37184, 'release': 'icehouse',
            'value': 1, 'type': 'Workflow',
            'review_id': uuidutils.generate_uuid()}
        yield mark


def _generate_review():
    yield {
        'status': 'NEW', 'review_number': 6, 'number': '60721',
        'module': 'glance', 'topic': 'bug/1258999', 'record_type': 'review',
        'value': -2, 'open': True,
        'id': uuidutils.generate_uuid(),
        'subject': 'Adding missing copy_from policy from policy.json',
        'user_id': 'john_doe',
        'primary_key': 'Ibc0d1fa7626629c28c514514a985a6b89db2ac69',
        'author_email': 'john_doe@gmail.com', 'company_name': '*independent',
        'branch': 'master',
        'launchpad_id': 'john_doe', 'lastUpdated': 1387865203,
        'author_name': 'John Doe', 'date': 1386547707,
        'url': 'https://review.openstack.org/60721',
        'sortKey': '0029f92e0000ed31', 'project': 'openstack/glance',
        'week': 2292, 'release': 'icehouse', 'updated_on': 1387865147
    }


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
    for key, value in six.iteritems(kwargs):
        position_to_key[len(values)] = key
        values.append(value)

    for chain in itertools.product(*values):
        result = {}
        for position, key in six.iteritems(position_to_key):
            result[key] = chain[position]
        yield result


def load_json(api_response):
    return json.loads(api_response.data.decode('utf8'))
