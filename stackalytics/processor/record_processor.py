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

        self.modules = None

        self.updated_users = set()

    def _get_release(self, timestamp):
        release_index = bisect.bisect(self.releases_dates, timestamp)
        return self.releases[release_index]['release_name']

    def _get_modules(self):
        if self.modules is None:
            self.modules = set()
            for repo in utils.load_repos(self.runtime_storage_inst):
                module = repo['module'].lower()
                add = True
                for m in self.modules:
                    if module.find(m) >= 0:
                        add = False
                        break
                    if m.find(module) >= 0:
                        self.modules.remove(m)
                        break
                if add:
                    self.modules.add(module)

        return self.modules

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

    def _get_lp_info(self, email):
        lp_profile = None
        if not utils.check_email_validity(email):
            LOG.debug('User email is not valid %s' % email)
        else:
            LOG.debug('Lookup user email %s at Launchpad' % email)
            uri = ('https://api.launchpad.net/1.0/people/?'
                   'ws.op=getByEmail&email=%s' % email)
            lp_profile = utils.read_json_from_uri(uri)

        if not lp_profile:
            LOG.debug('User with email %s not found', email)
            return None, None

        LOG.debug('Email is mapped to launchpad user: %s', lp_profile['name'])
        return lp_profile['name'], lp_profile['display_name']

    def _get_independent(self):
        return self.domains_index['']

    def _update_user_profile(self, user, email):
        LOG.debug('Add email %s to user %s', email, user['user_id'])
        user['emails'].append(email)
        company_name = self._get_company_by_email(email)
        if ((company_name) and (len(user['companies']) == 1) and
                (user['companies'][0]['company_name'] != company_name)):
            LOG.debug('Updating affiliation of user %s to %s',
                      user['user_id'], company_name)
            user['companies'][0]['company_name'] = company_name
            self.updated_users.add(user['user_id'])

    def update_user(self, record):
        email = record['author_email']

        if email in self.users_index:
            user = self.users_index[email]
        else:
            if ('launchpad_id' in record) and (record['launchpad_id']):
                launchpad_id = record['launchpad_id']
                user_name = record['author_name']
            else:
                launchpad_id, user_name = self._get_lp_info(email)

            if (launchpad_id) and (launchpad_id in self.users_index):
                # merge emails
                user = self.users_index[launchpad_id]
                self._update_user_profile(user, email)
            else:
                # create new
                if not user_name:
                    user_name = record['author_name']
                user = self._create_user(launchpad_id, email, user_name)

            utils.store_user(self.runtime_storage_inst, user)
            self.users_index[email] = user
            if user['launchpad_id']:
                self.users_index[user['launchpad_id']] = user

        return user

    def _update_record_and_user(self, record):
        user = self.update_user(record)

        record['user_id'] = user['user_id']
        record['launchpad_id'] = user['launchpad_id']

        if ('user_name' in user) and (user['user_name']):
            record['author_name'] = user['user_name']

        company = self._find_company(user['companies'], record['date'])
        if company != '*robots':
            company = (self._get_company_by_email(record['author_email'])
                       or company)
        record['company_name'] = company

    def _process_commit(self, record):
        record['primary_key'] = record['commit_id']
        record['loc'] = record['lines_added'] + record['lines_deleted']
        record['author_email'] = record['author_email'].lower()

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
        review['author_email'] = owner['email'].lower()
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
                mark['author_email'] = reviewer['email'].lower()
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

    def _guess_module(self, record):
        subject = record['subject'].lower()
        pos = len(subject)
        best_guess_module = None

        for module in self._get_modules():
            find = subject.find(module)
            if (find >= 0) and (find < pos):
                pos = find
                best_guess_module = module

        if best_guess_module:
            if (((pos > 0) and (subject[pos - 1] == '[')) or
                    (not record.get('module'))):
                record['module'] = best_guess_module

        if not record.get('module'):
            record['module'] = 'unknown'

    def _process_email(self, record):
        record['primary_key'] = record['message_id']
        record['author_email'] = record['author_email'].lower()

        self._update_record_and_user(record)
        self._guess_module(record)

        yield record

    def _apply_type_based_processing(self, record):
        if record['record_type'] == 'commit':
            for r in self._process_commit(record):
                yield r
        elif record['record_type'] == 'review':
            for r in self._process_review(record):
                yield r
        elif record['record_type'] == 'email':
            for r in self._process_email(record):
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
            author_name = record['author_name']

            self._update_record_and_user(record)

            if ((record['company_name'] != company_name) or
                    (record['user_id'] != user_id) or
                    (record['author_name'] != author_name)):
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

    def _get_records_for_users_to_update(self):
        for record in self.runtime_storage_inst.get_all_records():
            user_id = record['user_id']
            if user_id in self.updated_users:
                user = self.users_index[user_id]
                user_company_name = user['companies'][0]['company_name']
                if record['company_name'] != user_company_name:
                    LOG.debug('Record company will be changed to: %s',
                              user_company_name)
                    record['company_name'] = user_company_name
                    yield record

    def finalize(self):
        self.runtime_storage_inst.set_records(
            self._get_records_for_users_to_update())
