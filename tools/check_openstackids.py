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

# This utility compares user profiles from default_data.json and
# OpenStackID service. For every user it prints a plus sign if at least one
# email is registered in OpenStackID service and dollar sign if user
# affiliation matches. In the end the overall stats are printed. Full
# comparison is written into yaml file.

from __future__ import print_function

import functools
import json
import sys
import time

from oslo_config import cfg
import six
import yaml

from stackalytics.processor import openstackid_utils
from stackalytics.processor import user_processor
from stackalytics.processor import utils


def _read_raw_file(file_name):
    if six.PY3:
        opener = functools.partial(open, encoding='utf8')
    else:
        opener = open
    with opener(file_name, 'r') as content_file:
        return content_file.read()


def _read_file(file_name):
    return json.loads(_read_raw_file(file_name))


def get_domains_index(companies):
    domains_index = {}
    for company in companies:
        for domain in company['domains']:
            domains_index[domain] = company['company_name']

        if 'aliases' in company:
            for alias in company['aliases']:
                normalized_alias = utils.normalize_company_name(alias)
                domains_index[normalized_alias] = company['company_name']
        normalized_company_name = utils.normalize_company_name(
            company['company_name'])
        domains_index[normalized_company_name] = company['company_name']

    return domains_index


def flatten_companies(cs):
    return [{c['company_name']: c['end_date'] or 0} for c in cs]


def main():
    default_data = _read_file('etc/default_data.json')
    users = default_data['users']
    domains_index = get_domains_index(default_data['companies'])

    user_maps = 0
    email_maps_to_openstack_id = 0
    email_does_not_map_to_openstack_id = 0
    users_whos_email_does_not_map = 0
    name_differs = 0
    users_with_companies_match = 0

    recs = []

    for idx, user in enumerate(users):
        name = user['user_name']
        affiliation = flatten_companies(user['companies'])

        print(idx, name, end='')

        ce = []
        umn = 0
        companies_match = True

        for email in user['emails']:
            p = openstackid_utils.user_profile_by_email(email)

            if p:
                mapped_companies = user_processor.resolve_companies_aliases(
                    domains_index, p['companies'])
                email_maps_to_openstack_id += 1

                if p['user_name'] != name:
                    name_differs += 1

                ce.append({email: [p['user_name'],
                                   flatten_companies(mapped_companies)]})

                f = False
                if len(user['companies']) == 1:
                    dd_c = user['companies'][0]['company_name']
                    mc = [c['company_name'] for c in mapped_companies
                          if c['company_name'] != user_processor.INDEPENDENT]
                    if len(mc) == 1:
                        if dd_c == mc[0]:
                            f = True
                companies_match = companies_match and f
            else:
                email_does_not_map_to_openstack_id += 1
                umn += 1

        mark = ''

        if ce:
            recs.append([name, affiliation, ce])
            user_maps += 1
            mark = '+'

        if umn:
            users_whos_email_does_not_map += 1

        if ce and companies_match:
            users_with_companies_match += 1
            mark += '$'

        print('', mark)
        time.sleep(1.1)  # avoid throttling

    recs.sort(key=lambda x: x[0])

    meta = {
        'Default data profiles': len(users),
        'Profiles mapped': user_maps,
        'Profiles NOT mapped': len(users) - user_maps,
        'Profiles with emails NOT mapped': users_whos_email_does_not_map,
        'Emails mapped': email_maps_to_openstack_id,
        'Emails NOT mapped': email_does_not_map_to_openstack_id,
        'Names differ': name_differs,
        'Users with companies MATCH': users_with_companies_match,
    }
    print()
    yaml.safe_dump(meta, sys.stdout, default_flow_style=False)

    with open('profile_mapping.yaml', 'w') as fd:
        yaml.safe_dump(recs, fd, default_flow_style=False)


if __name__ == '__main__':
    opts = [
        cfg.IntOpt('read-timeout', default=20)
    ]
    cfg.CONF.register_opts(opts)
    cfg.CONF(project='stackalytics')

    main()
