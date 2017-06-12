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

import six

from stackalytics.processor import user_processor
from stackalytics.processor import utils


def _normalize_user(user):
    for c in user['companies']:
        c['end_date'] = utils.date_to_timestamp(c['end_date'])

    # sort companies by end_date
    def end_date_comparator(x, y):
        if x["end_date"] == 0:
            return 1
        elif y["end_date"] == 0:
            return -1
        else:
            return x["end_date"] - y["end_date"]

    user['companies'].sort(key=utils.cmp_to_key(end_date_comparator))
    if user['companies']:
        if user['companies'][-1]['end_date'] != 0:
            user['companies'].append(dict(company_name='*independent',
                                          end_date=0))
    user['user_id'] = user_processor.make_user_id(
        launchpad_id=user.get('launchpad_id'),
        emails=user.get('emails'))


def _normalize_users(users):
    for user in users:
        _normalize_user(user)


def _normalize_releases(releases):
    for release in releases:
        release['release_name'] = release['release_name'].lower()
        release['end_date'] = utils.date_to_timestamp(release['end_date'])
    releases.sort(key=lambda x: x['end_date'])


def _normalize_repos(repos):
    for repo in repos:
        if 'releases' not in repo:
            repo['releases'] = []  # release will be assigned automatically


NORMALIZERS = {
    'users': _normalize_users,
    'releases': _normalize_releases,
    'repos': _normalize_repos,
}


def normalize_default_data(default_data):
    for key, normalizer in six.iteritems(NORMALIZERS):
        if key in default_data:
            normalizer(default_data[key])
