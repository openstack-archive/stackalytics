# Copyright (c) 2016 OpenStack Foundation
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

import datetime
import time

import itertools
from oslo_log import log as logging
import requests

from stackalytics.processor import utils


LOG = logging.getLogger(__name__)

DAY = 24 * 60 * 60
WEEK = 7 * DAY

ZANATA_URI = 'https://translate.openstack.org/rest/%s'
ZANATA_FIRST_RECORD = '2015-08-31'  # must be Monday

zanata_session = requests.Session()


def _zanata_get_user_stats(zanata_user_id, start_date, end_date):
    uri = ZANATA_URI % ('stats/user/%s/%s..%s' % (zanata_user_id,
                        start_date, end_date))
    return utils.read_json_from_uri(uri, session=zanata_session)


def _timestamp_to_date(timestamp):
    return datetime.datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d')


def _date_to_timestamp(d):
    return int(time.mktime(
        datetime.datetime.strptime(d, '%Y-%m-%d').timetuple()))


def log(runtime_storage_inst, translation_team_uri):

    last_update_key = 'zanata:last_update'
    last_update = int(runtime_storage_inst.get_by_key(last_update_key) or
                      _date_to_timestamp(ZANATA_FIRST_RECORD))
    LOG.info('Last update: %d', last_update)
    now = int(time.time())

    LOG.info('Reading translation team from uri: %s', translation_team_uri)
    translation_team = utils.read_yaml_from_uri(translation_team_uri)

    if not translation_team:
        LOG.warning('Translation team data is not available')
        return

    user_ids = set(u['zanata_id'] for u in runtime_storage_inst.get_all_users()
                   if 'zanata_id' in u)
    user_ids |= set(itertools.chain.from_iterable(
        team.get('translators', []) for team in translation_team.values()))

    for user_id in user_ids:
        for day in range(last_update, now, WEEK):
            day_str = _timestamp_to_date(day)
            end_str = _timestamp_to_date(day + WEEK - DAY)
            user_stats = _zanata_get_user_stats(user_id, day_str, end_str)
            if user_stats:
                for user_stats_item in user_stats:
                    # Currently we only count translated words
                    if user_stats_item['savedState'] == 'Translated':
                        record = dict(
                            zanata_id=user_id,
                            date=_date_to_timestamp(
                                user_stats_item['savedDate']),
                            language_code=user_stats_item['localeId'],
                            language=user_stats_item['localeDisplayName'],
                            # Todo: not always consistent to the official name
                            module=user_stats_item['projectSlug'],
                            # Since Zanata does not support '/' character
                            # in project version names, i18n uses '-' instead
                            # of '/' for branch names.
                            branch=user_stats_item['versionSlug'].replace(
                                '-', '/'),
                            translated=user_stats_item['wordCount'],
                        )
                        yield record
    last_update += (now - last_update) // WEEK * WEEK
    LOG.info('New last update: %d', last_update)
    runtime_storage_inst.set_by_key(last_update_key, last_update)
