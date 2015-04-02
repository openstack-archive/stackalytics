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


DEFAULT_DATA = {
    'users': [
        {
            'launchpad_id': 'john_doe',
            'user_name': 'John Doe',
            'emails': ['johndoe@gmail.com', 'jdoe@nec.com'],
            'companies': [
                {'company_name': '*independent', 'end_date': '2013-May-01'},
                {'company_name': 'NEC', 'end_date': None},
            ]
        },
        {
            'launchpad_id': 'smith',
            'user_name': 'Smith',
            'emails': ['smith@gmail.com', 'smith@nec.com'],
            'companies': [
                {'company_name': 'IBM', 'end_date': '2013-May-01'},
                {'company_name': 'NEC', 'end_date': '2014-Jun-01'}
            ]
        },
        {
            'launchpad_id': 'ivan_ivanov',
            'user_name': 'Ivan Ivanov',
            'emails': ['ivanivan@yandex.ru', 'iivanov@mirantis.com'],
            'companies': [
                {'company_name': 'Mirantis', 'end_date': None},
            ]
        }
    ],
    'companies': [
        {
            'company_name': '*independent',
            'domains': ['']
        },
        {
            'company_name': 'NEC',
            'domains': ['nec.com', 'nec.co.jp']
        },
        {
            'company_name': 'Mirantis',
            'domains': ['mirantis.com', 'mirantis.ru']
        },
    ],
    'repos': [
        {
            'branches': ['master'],
            'module': 'stackalytics',
            'project_type': 'stackforge',
            'uri': 'git://git.openstack.org/stackforge/stackalytics.git'
        }
    ],
    'releases': [
        {
            'release_name': 'prehistory',
            'end_date': '2011-Apr-21'
        },
        {
            'release_name': 'Havana',
            'end_date': '2013-Oct-17'
        }
    ]
}

USERS = DEFAULT_DATA['users']
REPOS = DEFAULT_DATA['repos']
COMPANIES = DEFAULT_DATA['companies']
RELEASES = DEFAULT_DATA['releases']
