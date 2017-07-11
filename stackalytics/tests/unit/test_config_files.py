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

import functools
import json
import os
import stat

import jsonschema
import six
import testtools

from stackalytics.processor import normalizer
from stackalytics.processor import schema as coded_schema


IGNORED_COMPANIES = ['*robots', 'April', 'Chelsio Communications',
                     'CloudRunner.io', 'Datera', 'Facebook',
                     'Fermi National Accelerator Laboratory', 'Github',
                     'H3C',
                     'Huaxin Hospital, First Hospital of Tsinghua University',
                     'InfluxDB', 'Kickstarter', 'National Security Agency',
                     'OpenStack Foundation', 'OpenStack Korea User Group',
                     'ProphetStor', 'SVA System Vertrieb Alexander GmbH',
                     'Sencha', 'Stark & Wayne LLC', 'Styra',
                     'Suranee University of Technology',
                     'The Linux Foundation', 'UTi Worldwide', 'Undead Labs',
                     'Violin Memory', 'docCloud', 'npm']


def dict_raise_on_duplicates(ordered_pairs):
    """Reject duplicate keys."""
    d = {}
    for k, v in ordered_pairs:
        if k in d:
            raise ValueError("duplicate key: %s (value: %s)" % (k, v))
        else:
            d[k] = v
    return d


class TestConfigFiles(testtools.TestCase):

    def _read_raw_file(self, file_name):
        if six.PY3:
            opener = functools.partial(open, encoding='utf8')
        else:
            opener = open
        with opener(file_name, 'r') as content_file:
            return content_file.read()

    def _read_file(self, file_name):
        return json.loads(self._read_raw_file(file_name))

    def _verify_ordering(self, array, key, msg):
        comparator = lambda x, y: (x > y) - (x < y)

        diff_msg = ''
        for i in range(len(array) - 1):
            if comparator(key(array[i]), key(array[i + 1])) > 0:
                diff_msg = ('Order fails at index %(index)s, '
                            'elements:\n%(first)s:\n%(second)s' %
                            {'index': i, 'first': array[i],
                             'second': array[i + 1]})
                break
        if diff_msg:
            self.fail(msg + '\n' + diff_msg)

    def test_corrections(self):
        corrections = self._read_file('etc/corrections.json')
        schema = self._read_file('etc/corrections.schema.json')
        jsonschema.validate(corrections, schema)

    def _verify_default_data_duplicate_keys(self, file_name):
        try:
            json.loads(self._read_raw_file(file_name),
                       object_pairs_hook=dict_raise_on_duplicates)
        except ValueError as ve:
            self.fail(ve)

    def test_default_data_duplicate_keys(self):
        self._verify_default_data_duplicate_keys('etc/default_data.json')

    def test_test_default_data_duplicate_keys(self):
        self._verify_default_data_duplicate_keys('etc/test_default_data.json')

    def _verify_default_data_by_schema(self, file_name):
        default_data = self._read_file(file_name)
        try:
            jsonschema.validate(default_data, coded_schema.default_data)
        except jsonschema.ValidationError as e:
            self.fail(e)

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
            users, key=lambda x: (x.get('launchpad_id') or x.get('github_id')),
            msg='List of users should be ordered by launchpad id or ldap id '
                'or github id')

    def test_users_in_alphabetical_order(self):
        self._verify_users_in_alphabetical_order('etc/default_data.json')

    def test_users_in_alphabetical_order_in_test_file(self):
        self._verify_users_in_alphabetical_order('etc/test_default_data.json')

    def _check_collision(self, storage, user, field, field_name):
        self.assertNotIn(
            field, storage,
            'Duplicate %s %s, collision between: %s and %s'
            % (field_name, field, storage[field], user))
        storage[field] = user

    def _verify_users_unique(self, file_name):
        users = self._read_file(file_name)['users']
        storage = {}
        for user in users:
            if user.get('launchpad_id'):
                field = user['launchpad_id']
                self.assertNotIn(
                    field, storage,
                    'Duplicate launchpad_id %s, collision between: %s and %s'
                    % (field, storage.get(field), user))
                storage[field] = user

            if user.get('gerrit_id'):
                field = user['gerrit_id']
                self.assertNotIn(
                    ('gerrit:%s' % field), storage,
                    'Duplicate gerrit_id %s, collision between: %s and %s'
                    % (field, storage.get(field), user))
                storage['gerrit:%s' % field] = user

            for email in user['emails']:
                self.assertNotIn(
                    email, storage,
                    'Duplicate email %s, collision between: %s and %s'
                    % (email, storage.get(email), user))
                storage[email] = user

    def test_users_unique_profiles(self):
        self._verify_users_unique('etc/default_data.json')

    def test_users_unique_profiles_in_test_file(self):
        self._verify_users_unique('etc/test_default_data.json')

    def _verify_default_data_whitespace_issues(self, file_name):
        data = self._read_raw_file(file_name)
        line_n = 1
        for line in data.split('\n'):
            msg = 'Whitespace issue in "%s", line %s: ' % (line, line_n)
            self.assertEqual(-1, line.find('\t'),
                             message=msg + 'tab character')
            self.assertEqual(line.rstrip(), line,
                             message=msg + 'trailing spaces')
            line_n += 1

    def test_default_data_whitespace_issues(self):
        self._verify_default_data_whitespace_issues('etc/default_data.json')

    def test_test_default_data_whitespace_issues(self):
        self._verify_default_data_whitespace_issues(
            'etc/test_default_data.json')

    def _validate_default_data_correctness(self, file_name):
        data = self._read_file(file_name)
        normalizer.normalize_default_data(data)

    def test_default_data_user_profiles_correctness(self):
        self._validate_default_data_correctness('etc/default_data.json')

    def test_test_default_data_user_profiles_correctness(self):
        self._validate_default_data_correctness('etc/test_default_data.json')

    def _validate_user_companies(self, file_name):
        data = self._read_file(file_name)
        users = data['users']
        companies = data['companies']
        company_names = []
        for company in companies:
            company_names.append(company['company_name'])
            for alias in company.get('aliases', []):
                company_names.append(alias)

        for user in users:
            for company in user['companies']:
                if not company['company_name'] in IGNORED_COMPANIES:
                    error_msg = ('Company "%s" is unknown. Please add it into'
                                 ' the list of companies in default_data.json '
                                 'file' % company['company_name'])
                    self.assertIn(company['company_name'], company_names,
                                  error_msg)

    def test_default_data_user_companies(self):
        self._validate_user_companies('etc/default_data.json')

    def test_test_default_data_user_companies(self):
        self._validate_user_companies('etc/test_default_data.json')

    def test_file_mode(self):
        files = os.listdir('etc')
        for f in ('etc/%s' % f for f in files):
            st = os.stat(f)
            x_flag = stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH
            self.assertFalse(bool(st.st_mode & x_flag),
                             msg='File %s should not be executable' % f)

    def _verify_users_one_open_interval(self, file_name):
        users = self._read_file(file_name)['users']
        for user in users:
            ops = set([])
            for c in user['companies']:
                if not c['end_date']:
                    ops.add(c['company_name'])

            self.assertLessEqual(
                len(ops), 1, msg='More than 1 company is specified '
                                 'as current: %s. Please keep '
                                 'only one' % ', '.join(ops))

    def test_default_data_users_one_open_interval(self):
        self._verify_users_one_open_interval('etc/default_data.json')

    def test_test_default_data_users_one_open_interval(self):
        self._verify_users_one_open_interval('etc/test_default_data.json')
