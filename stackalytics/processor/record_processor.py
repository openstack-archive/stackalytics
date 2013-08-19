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

import bisect
import re

from stackalytics.openstack.common import log as logging
from stackalytics.processor import normalizer
from stackalytics.processor import utils

LOG = logging.getLogger(__name__)


class RecordProcessor(object):
    def __init__(self, runtime_storage_inst):
        self.runtime_storage_inst = runtime_storage_inst

        self.domains_index = runtime_storage_inst.get_by_key('companies')

        self.users_index = runtime_storage_inst.get_by_key('users')

        self.releases = runtime_storage_inst.get_by_key('releases')
        self.releases_dates = [r['end_date'] for r in self.releases]

    def _get_release(self, timestamp):
        release_index = bisect.bisect(self.releases_dates, timestamp)
        return self.releases[release_index]['release_name']

    def _find_company(self, companies, date):
        for r in companies:
            if date < r['end_date']:
                return r['company_name']
        return companies[-1]['company_name']

    def _get_company_by_email(self, email):
        name, at, domain = email.partition('@')
        if domain:
            parts = domain.split('.')
            for i in range(len(parts), 1, -1):
                m = '.'.join(parts[len(parts) - i:])
                if m in self.domains_index:
                    return self.domains_index[m]
        return None

    def _create_user(self, launchpad_id, email, user_name):
        company = (self._get_company_by_email(email) or
                   self._get_independent())
        user = {
            'user_id': normalizer.get_user_id(launchpad_id, email),
            'launchpad_id': launchpad_id,
            'user_name': user_name,
            'emails': [email],
            'companies': [{
                'company_name': company,
                'end_date': 0,
            }],
        }
        normalizer.normalize_user(user)
        LOG.debug('Create new user: %s', user)
        return user

    def _store_user(self, user):
        self.runtime_storage_inst.set_by_key('user:%s' % user['user_id'], user)

    def _get_lp_info(self, email):
        lp_profile = None
        if not re.match(r'[\w\d_\.-]+@([\w\d_\.-]+\.)+[\w]+', email):
            LOG.debug('User email is not valid %s' % email)
        else:
            LOG.debug('Lookup user email %s at Launchpad' % email)
            uri = ('https://api.launchpad.net/1.0/people/?'
                   'ws.op=getByEmail&email=%s' % email)
            lp_profile = utils.read_json_from_uri(uri)

        if not lp_profile:
            LOG.debug('User with email %s not found', email)
            return None, None

        return lp_profile['name'], lp_profile['display_name']

    def _get_independent(self):
        return self.domains_index['']

    def _update_record_and_user(self, record):
        email = record['author_email'].lower()
        record['author_email'] = email

        if email in self.users_index:
            user = self.users_index[email]
            record['launchpad_id'] = user['launchpad_id']
        else:
            if ('launchpad_id' in record) and (record['launchpad_id']):
                user = self._create_user(record['launchpad_id'], email,
                                         record['author_name'])
            else:
                launchpad_id, user_name = self._get_lp_info(email)
                record['launchpad_id'] = launchpad_id

                if (launchpad_id) and (launchpad_id in self.users_index):
                    # merge emails
                    user = self.users_index[launchpad_id]
                    user['emails'].append(email)
                else:
                    # create new
                    if not user_name:
                        user_name = record['author_name']
                    user = self._create_user(launchpad_id, email, user_name)

            self._store_user(user)
            self.users_index[email] = user
            if user['launchpad_id']:
                self.users_index[user['launchpad_id']] = user

        record['user_id'] = user['user_id']

        company_by_user = self._find_company(user['companies'], record['date'])
        if company_by_user == '*robots':
            # don't map robots by email
            company = company_by_user
        else:
            company = self._get_company_by_email(email)
            if not company:
                company = company_by_user
        record['company_name'] = company

        if ('user_name' in user) and (user['user_name']):
            record['author_name'] = user['user_name']

    def _process_commit(self, record):
        record['primary_key'] = record['commit_id']
        record['loc'] = record['lines_added'] + record['lines_deleted']

        self._update_record_and_user(record)

        if record['company_name'] != '*robots':
            yield record

    def _spawn_review(self, record):
        # copy everything except pathsets and flatten user data
        review = dict([(k, v) for k, v in record.iteritems()
                       if k not in ['patchSets', 'owner', 'createdOn']])
        owner = record['owner']
        if 'email' not in owner or 'username' not in owner:
            return  # ignore

        review['primary_key'] = review['id']
        review['launchpad_id'] = owner['username']
        review['author_name'] = owner['name']
        review['author_email'] = owner['email']
        review['date'] = record['createdOn']

        self._update_record_and_user(review)

        yield review

    def _spawn_marks(self, record):
        review_id = record['id']
        module = record['module']

        for patch in record['patchSets']:
            if 'approvals' not in patch:
                continue  # not reviewed by anyone
            for approval in patch['approvals']:
                # copy everything and flatten user data
                mark = dict([(k, v) for k, v in approval.iteritems()
                             if k not in ['by', 'grantedOn']])
                reviewer = approval['by']

                if 'email' not in reviewer or 'username' not in reviewer:
                    continue  # ignore

                mark['record_type'] = 'mark'
                mark['date'] = approval['grantedOn']
                mark['primary_key'] = (record['id'] +
                                       str(mark['date']) +
                                       mark['type'])
                mark['launchpad_id'] = reviewer['username']
                mark['author_name'] = reviewer['name']
                mark['author_email'] = reviewer['email']
                mark['module'] = module
                mark['review_id'] = review_id

                self._update_record_and_user(mark)

                yield mark

    def _process_review(self, record):
        """
         Process a review. Review spawns into records of two types:
          * review - records that a user created review request
          * mark - records that a user set approval mark to given review
        """
        for gen in [self._spawn_review, self._spawn_marks]:
            for r in gen(record):
                yield r

    def _apply_type_based_processing(self, record):
        if record['record_type'] == 'commit':
            for r in self._process_commit(record):
                yield r
        elif record['record_type'] == 'review':
            for r in self._process_review(record):
                yield r

    def process(self, record_iterator):
        for record in record_iterator:
            for r in self._apply_type_based_processing(record):

                if r['company_name'] == '*robots':
                    continue

                r['week'] = utils.timestamp_to_week(r['date'])
                if ('release' not in r) or (not r['release']):
                    r['release'] = self._get_release(r['date'])

                yield r

        self.runtime_storage_inst.set_by_key('users', self.users_index)

    def update(self, record_iterator, release_index):
        for record in record_iterator:
            need_update = False

            company_name = record['company_name']
            user_id = record['user_id']

            self._update_record_and_user(record)

            if ((record['company_name'] != company_name) or
                    (record['user_id'] != user_id)):
                need_update = True

            if record['primary_key'] in release_index:
                release = release_index[record['primary_key']]
            else:
                release = self._get_release(record['date'])

            if record['release'] != release:
                need_update = True
                record['release'] = release

            if need_update:
                yield record

        self.runtime_storage_inst.set_by_key('users', self.users_index)
