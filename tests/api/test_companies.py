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

from tests.api import test_api


class TestAPICompanies(test_api.TestAPI):

    def test_get_companies(self):
        with test_api.make_runtime_storage(
                {'repos': [{'module': 'nova', 'project_type': 'openstack',
                            'organization': 'openstack',
                            'uri': 'git://github.com/openstack/nova.git'},
                           {'module': 'glance', 'project_type': 'openstack',
                            'organization': 'openstack',
                            'uri': 'git://github.com/openstack/glance.git'}]},
                test_api.make_records(record_type=['commit'],
                                      loc=[10, 20, 30],
                                      module=['glance'],
                                      company_name=['NEC', 'IBM', 'NTT']),
                test_api.make_records(record_type=['review'],
                                      primary_key=['0123456789', '9876543210'],
                                      company_name=['IBM']),
                test_api.make_records(record_type=['mark'],
                                      review_id=['0123456789', '9876543210'],
                                      company_name=['IBM']),
                test_api.make_records(record_type=['mark'],
                                      review_id=['0123456789'],
                                      company_name=['NEC'])):

            response = self.app.get('/api/1.0/companies?metric=commits')
            companies = json.loads(response.data)['companies']
            self.assertEqual([{'id': 'ibm', 'text': 'IBM'},
                              {'id': 'nec', 'text': 'NEC'},
                              {'id': 'ntt', 'text': 'NTT'}], companies)

            response = self.app.get('/api/1.0/companies?metric=marks')
            companies = json.loads(response.data)['companies']
            self.assertEqual([{'id': 'ibm', 'text': 'IBM'},
                              {'id': 'nec', 'text': 'NEC'}], companies)

            response = self.app.get('/api/1.0/companies?metric=commits&'
                                    'company_name=ib')
            companies = json.loads(response.data)['companies']
            self.assertEqual([{'id': 'ibm', 'text': 'IBM'}], companies)

    def test_get_company(self):
        with test_api.make_runtime_storage(
                {'repos': [{'module': 'nova', 'project_type': 'openstack',
                            'organization': 'openstack',
                            'uri': 'git://github.com/openstack/nova.git'},
                           {'module': 'glance', 'project_type': 'openstack',
                            'organization': 'openstack',
                            'uri': 'git://github.com/openstack/glance.git'}]},
                test_api.make_records(record_type=['commit'],
                                      loc=[10, 20, 30],
                                      module=['glance'],
                                      company_name=['NEC', 'IBM', 'NTT'])):

            response = self.app.get('/api/1.0/companies/nec')
            company = json.loads(response.data)['company']
            self.assertEqual({'id': 'nec', 'text': 'NEC'}, company)

            response = self.app.get('/api/1.0/companies/google')
            self.assertEqual(404, response.status_code)
