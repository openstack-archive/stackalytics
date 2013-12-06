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
import time

from stackalytics.openstack.common import log as logging
from stackalytics.processor import launchpad_utils
from stackalytics.processor import normalizer
from stackalytics.processor import utils

LOG = logging.getLogger(__name__)


class RecordProcessor(object):
    def __init__(self, runtime_storage_inst):
        self.runtime_storage_inst = runtime_storage_inst

        self.domains_index = runtime_storage_inst.get_by_key('companies')

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
        if not email:
            return None

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
            'user_name': user_name or '',
            'companies': [{
                'company_name': company,
                'end_date': 0,
            }],
        }
        if email:
            user['emails'] = [email]
        else:
            user['emails'] = []
        normalizer.normalize_user(user)
        return user

    def _get_lp_info(self, email):
        lp_profile = None
        if not utils.check_email_validity(email):
            LOG.debug('User email is not valid %s', email)
        else:
            lp_profile = launchpad_utils.lp_profile_by_email(email)

        if not lp_profile:
            LOG.debug('User with email %s not found', email)
            return None, None

        LOG.debug('Email is mapped to launchpad user: %s', lp_profile['name'])
        return lp_profile['name'], lp_profile['display_name']

    def _get_lp_user_name(self, launchpad_id):
        if not launchpad_id:
            return None

        lp_profile = launchpad_utils.lp_profile_by_launchpad_id(launchpad_id)

        if not lp_profile:
            LOG.debug('User with id %s not found', launchpad_id)
            return launchpad_id

        return lp_profile['display_name']

    def _get_independent(self):
        return '*independent'

    def _update_user_affiliation(self, user):
        for email in user.get('emails'):
            company_name = self._get_company_by_email(email)
            uc = user['companies']
            if (company_name and (len(uc) == 1) and
                    (uc[0]['company_name'] == self._get_independent())):
                LOG.debug('Updating affiliation of user %s to %s',
                          user['user_id'], company_name)
                uc[0]['company_name'] = company_name
                self.updated_users.add(user['user_id'])
                break

    def _get_user_exact_company(self, user):
        if len(user.get('companies', [])) == 1:
            return user['companies'][0]['company_name']
        return None

    def _merge_user_profiles(self, user_a, user_b, user_c):
        user = {}
        for key in ['seq', 'user_name', 'user_id',
                    'launchpad_id', 'companies']:
            user[key] = user_a.get(key) or user_b.get(key) or user_c.get(key)

        if user['launchpad_id'] and user['user_id'] != user['launchpad_id']:
            self.updated_users.add(user['user_id'])
            user['user_id'] = user['launchpad_id']

        emails = set([])
        core_in = set([])
        for u in [user_a, user_b, user_c]:
            emails |= set(u.get('emails', []))
            core_in |= set(u.get('core', []))
        user['emails'] = list(emails)
        user['core'] = list(core_in)

        self._update_user_affiliation(user)
        if (self._get_user_exact_company(user_b) and
                (self._get_user_exact_company(user)
                 != self._get_user_exact_company(user_b))):
            # affiliation changed automatically
            self.updated_users.add(user_b['user_id'])

        if user_a.get('seq') and user_b.get('seq'):
            LOG.debug('Delete user: %s', user_b)
            utils.delete_user(self.runtime_storage_inst, user_b)
        return user

    def update_user(self, record):
        email = record.get('author_email')
        user_e = utils.load_user(self.runtime_storage_inst, email) or {}

        user_name = record.get('author_name')
        launchpad_id = record.get('launchpad_id')
        if email and (not user_e) and (not launchpad_id):
            # query LP
            launchpad_id, lp_user_name = self._get_lp_info(email)
            if lp_user_name:
                user_name = lp_user_name

        user_l = utils.load_user(self.runtime_storage_inst, launchpad_id) or {}

        user = self._create_user(launchpad_id, email, user_name)

        if (user_e.get('seq') == user_l.get('seq')) and user_e.get('seq'):
            # sequence numbers are set and the same, merge is not needed
            user = user_e
        else:
            if user_e or user_l:
                user = self._merge_user_profiles(user_e, user_l, user)
            else:
                # create new
                if not user_name:
                    user_name = self._get_lp_user_name(launchpad_id)
                    if user_name:
                        user['user_name'] = user_name
                LOG.debug('Created new user: %s', user)

            utils.store_user(self.runtime_storage_inst, user)

        return user

    def _update_record_and_user(self, record):
        user = self.update_user(record)

        record['user_id'] = user['user_id']
        record['launchpad_id'] = user['launchpad_id']

        if user.get('user_name'):
            record['author_name'] = user['user_name']

        company = self._find_company(user['companies'], record['date'])
        if company != '*robots':
            company = (self._get_company_by_email(record.get('author_email'))
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
        # copy everything except patchsets and flatten user data
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

        patch_sets = record.get('patchSets', [])
        review['updated_on'] = review['date']
        review['patch_count'] = len(patch_sets)
        if patch_sets:
            patch = patch_sets[-1]
            if 'approvals' in patch:
                review['value'] = min([int(p['value'])
                                       for p in patch['approvals']])
                review['updated_on'] = patch['approvals'][0]['grantedOn']
            else:
                review['updated_on'] = patch['createdOn']

        if 'value' not in review:
            review['value'] = 0

        self._update_record_and_user(review)

        yield review

    def _spawn_marks(self, record):
        review_id = record['id']
        module = record['module']
        branch = record['branch']

        for patch in record.get('patchSets', []):
            if 'approvals' not in patch:
                continue  # not reviewed by anyone
            for approval in patch['approvals']:
                # copy everything and flatten user data
                mark = dict([(k, v) for k, v in approval.iteritems()
                             if k not in ['by', 'grantedOn', 'value']])
                reviewer = approval['by']

                if 'email' not in reviewer or 'username' not in reviewer:
                    continue  # ignore

                mark['record_type'] = 'mark'
                mark['value'] = int(approval['value'])
                mark['date'] = approval['grantedOn']
                mark['primary_key'] = (record['id'] +
                                       str(mark['date']) +
                                       mark['type'])
                mark['launchpad_id'] = reviewer['username']
                mark['author_name'] = reviewer['name']
                mark['author_email'] = reviewer['email'].lower()
                mark['module'] = module
                mark['branch'] = branch
                mark['review_id'] = review_id
                mark['patch'] = int(patch['number'])

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

        if not record.get('blueprint_id'):
            del record['body']

        yield record

    def _process_blueprint(self, record):
        bpd_author = record.get('drafter') or record.get('owner')

        bpd = dict([(k, v) for k, v in record.iteritems()
                    if k.find('_link') < 0])
        bpd['record_type'] = 'bpd'
        bpd['primary_key'] = 'bpd:' + record['id']
        bpd['launchpad_id'] = bpd_author
        bpd['date'] = record['date_created']

        self._update_record_and_user(bpd)

        yield bpd

        if record.get('assignee') and record['date_completed']:
            bpc = dict([(k, v) for k, v in record.iteritems()
                        if k.find('_link') < 0])
            bpc['record_type'] = 'bpc'
            bpc['primary_key'] = 'bpc:' + record['id']
            bpc['launchpad_id'] = record['assignee']
            bpc['date'] = record['date_completed']

            self._update_record_and_user(bpc)

            yield bpc

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
        elif record['record_type'] == 'bp':
            for r in self._process_blueprint(record):
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

    def _get_records_for_users_to_update(self):
        users_reviews = {}
        valid_blueprints = {}
        mentioned_blueprints = {}
        core_engineers = {}
        quarter_ago = int(time.time()) - 60 * 60 * 24 * 30 * 3  # a quarter ago
        for record in self.runtime_storage_inst.get_all_records():
            for bp in record.get('blueprint_id', []):
                if bp in mentioned_blueprints:
                    mentioned_blueprints[bp]['count'] += 1
                    if record['date'] > mentioned_blueprints[bp]['date']:
                        mentioned_blueprints[bp]['date'] = record['date']
                else:
                    mentioned_blueprints[bp] = {
                        'count': 1,
                        'date': record['date']
                    }
            if record['record_type'] in ['bpd', 'bpc']:
                valid_blueprints[record['id']] = {
                    'primary_key': record['primary_key'],
                    'count': 0,
                    'date': record['date']
                }

            if record['record_type'] == 'review':
                launchpad_id = record['launchpad_id']
                review = {'date': record['date'], 'id': record['id']}
                if launchpad_id in users_reviews:
                    users_reviews[launchpad_id].append(review)
                else:
                    users_reviews[launchpad_id] = [review]

        for bp_name, bp in valid_blueprints.iteritems():
            if bp_name in mentioned_blueprints:
                bp['count'] = mentioned_blueprints[bp_name]['count']
                bp['date'] = mentioned_blueprints[bp_name]['date']
            else:
                bp['count'] = 0
                bp['date'] = 0

        reviews_index = {}
        for launchpad_id, reviews in users_reviews.iteritems():
            reviews.sort(key=lambda x: x['date'])
            review_number = 0
            for review in reviews:
                review_number += 1
                review['review_number'] = review_number
                reviews_index[review['id']] = review

        for record in self.runtime_storage_inst.get_all_records():

            need_update = False

            if record['user_id'] in self.updated_users:
                user = utils.load_user(self.runtime_storage_inst,
                                       record['user_id'])
                user_company_name = user['companies'][0]['company_name']
                if record['company_name'] != user_company_name:
                    LOG.debug('Update record %s: company changed to: %s',
                              record['primary_key'], user_company_name)
                    record['company_name'] = user_company_name
                    need_update = True
                if record['user_id'] != user['user_id']:
                    LOG.debug('Update record %s, user id changed to: %s',
                              record['primary_key'], user['user_id'])
                    record['user_id'] = user['user_id']
                    need_update = True

            valid_bp = set([])
            for bp in record.get('blueprint_id', []):
                if bp in valid_blueprints:
                    valid_bp.add(bp)
                else:
                    LOG.debug('Update record %s: removed invalid bp: %s',
                              record['primary_key'], bp)
                    need_update = True
            record['blueprint_id'] = list(valid_bp)

            if record['record_type'] in ['bpd', 'bpc']:
                bp = valid_blueprints[record['id']]
                if ((record.get('mention_count') != bp['count']) or
                        (record.get('mention_date') != bp['date'])):
                    record['mention_count'] = bp['count']
                    record['mention_date'] = bp['date']
                    LOG.debug('Update record %s: mention stats: (%s:%s)',
                              record['primary_key'], bp['count'], bp['date'])
                    need_update = True

            if record['record_type'] == 'review':
                review = reviews_index[record['id']]
                if record.get('review_number') != review['review_number']:
                    record['review_number'] = review['review_number']
                    need_update = True

            if (record['record_type'] == 'mark' and
                    record['date'] > quarter_ago and
                    record['value'] in [2, -2]):
                module_branch = (record['module'], record['branch'])
                user_id = record['user_id']
                if user_id in core_engineers:
                    core_engineers[user_id].add(module_branch)
                else:
                    core_engineers[user_id] = set([module_branch])

            if need_update:
                yield record

        for user in self.runtime_storage_inst.get_all_users():
            core_old = user.get('core')
            user['core'] = list(core_engineers.get(user['user_id'], []))
            if user['core'] != core_old:
                utils.store_user(self.runtime_storage_inst, user)

    def _marks_with_disagreement(self):
        LOG.debug('Process marks to find disagreements')
        marks_per_patch = {}
        for record in self.runtime_storage_inst.get_all_records():
            if record['record_type'] == 'mark' and record['type'] == 'CRVW':
                review_id = record['review_id']
                patch_number = record['patch']
                if (review_id, patch_number) in marks_per_patch:
                    marks_per_patch[(review_id, patch_number)].append(record)
                else:
                    marks_per_patch[(review_id, patch_number)] = [record]

        cores = dict([(user['user_id'], user)
                      for user in self.runtime_storage_inst.get_all_users()
                      if user['core']])

        for key, marks in marks_per_patch.iteritems():
            if len(marks) < 2:
                continue

            core_mark = 0
            for mark in sorted(marks, key=lambda x: x['date'], reverse=True):

                if core_mark == 0:
                    user_id = mark['user_id']
                    if user_id in cores:
                        user = cores[user_id]
                        if (mark['module'], mark['branch']) in user['core']:
                            # mark is from core engineer
                            core_mark = mark['value']
                            continue

                disagreement = (core_mark != 0) and (
                    (core_mark < 0 < mark['value']) or
                    (core_mark > 0 > mark['value']))
                old_disagreement = mark.get('x')
                mark['x'] = disagreement
                if old_disagreement != disagreement:
                    yield mark

    def finalize(self):
        self.runtime_storage_inst.set_records(
            self._get_records_for_users_to_update())

        self.runtime_storage_inst.set_records(
            self._marks_with_disagreement())
