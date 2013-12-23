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

import json

import jsonschema
import testtools


class TestConfigFiles(testtools.TestCase):
    def setUp(self):
        super(TestConfigFiles, self).setUp()

    def _read_file(self, file_name):
        with open(file_name, 'r') as content_file:
            content = content_file.read()
            return json.loads(content)

    def _verify_ordering(self, array, key, msg):
        sorted_array = sorted(array, key=key)
        diff_msg = None
        for i in range(len(array)):
            if array[i] != sorted_array[i]:
                diff_msg = ('First differing element %s:\n%s\n%s' %
                            (i, array[i], sorted_array[i]))
        if diff_msg:
            self.fail(msg + '\n' + diff_msg)

    def test_corrections(self):
        corrections = self._read_file('etc/corrections.json')
        schema = self._read_file('etc/corrections.schema.json')
        jsonschema.validate(corrections, schema)

    def _verify_default_data_by_schema(self, file_name):
        default_data = self._read_file(file_name)
        schema = self._read_file('etc/default_data.schema.json')
        jsonschema.validate(default_data, schema)

    def test_default_data_schema_conformance(self):
        self._verify_default_data_by_schema('etc/default_data.json')

    def test_test_default_data_schema_conformance(self):
        self._verify_default_data_by_schema('etc/test_default_data.json')

    def _verify_companies_in_alphabetical_order(self, file_name):
        companies = self._read_file(file_name)['companies']
        self._verify_ordering(
            companies, key=lambda x: x['domains'][0],
            msg='List of companies should be ordered by the first domain')

    def test_companies_in_alphabetical_order(self):
        self._verify_companies_in_alphabetical_order('etc/default_data.json')

    def test_companies_in_alphabetical_order_in_test_file(self):
        self._verify_companies_in_alphabetical_order(
            'etc/test_default_data.json')

    def _verify_users_in_alphabetical_order(self, file_name):
        users = self._read_file(file_name)['users']
        self._verify_ordering(
            users, key=lambda x: x['launchpad_id'],
            msg='List of users should be ordered by launchpad id')

    def test_users_in_alphabetical_order(self):
        self._verify_users_in_alphabetical_order('etc/default_data.json')

    def test_users_in_alphabetical_order_in_test_file(self):
        self._verify_users_in_alphabetical_order('etc/test_default_data.json')
