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
import re
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

# We limit the projects and versions to reduce number of requests to Zanata API
ZANATA_VERSION_PATTERN = re.compile(r'^(master)$')
ZANATA_PROJECT_PATTERN = re.compile(r'(horizon$|.*guide|.*manual)')

zanata_session = requests.Session()


def _zanata_get_projects():
    uri = ZANATA_URI % 'projects'
    LOG.debug("Reading projects from %s" % uri)
    projects_data = utils.read_json_from_uri(uri, session=zanata_session)

    return (p['id'] for p in projects_data
            if ZANATA_PROJECT_PATTERN.match(p['id']))


def _zanata_get_project_versions(project_id):
    LOG.debug("Reading iterations for project %s" % project_id)
    uri = ZANATA_URI % ('projects/p/%s' % project_id)
    project_data = utils.read_json_from_uri(uri, session=zanata_session)

    return (it['id'] for it in project_data.get('iterations', [])
            if ZANATA_VERSION_PATTERN.match(it['id']))


def _zanata_get_user_stats(project_id, iteration_id, zanata_user_id,
                           start_date, end_date):
    uri = ZANATA_URI % ('stats/project/%s/version/%s/contributor/%s/%s..%s'
                        % (project_id, iteration_id, zanata_user_id,
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

    languages = dict((k, v['language'][0])
                     for k, v in translation_team.items())

    user_ids = set(u['zanata_id'] for u in runtime_storage_inst.get_all_users()
                   if 'zanata_id' in u)
    user_ids |= set(itertools.chain.from_iterable(
        team.get('translators', []) for team in translation_team.values()))

    for project_id in _zanata_get_projects():
        for version in _zanata_get_project_versions(project_id):
            for user_id in user_ids:

                for day in range(last_update, now, WEEK):
                    day_str = _timestamp_to_date(day)
                    end_str = _timestamp_to_date(day + WEEK - DAY)

                    stats = _zanata_get_user_stats(
                        project_id, version, user_id, day_str, end_str)
                    user_stats = stats[user_id]

                    if user_stats:
                        for lang, data in user_stats.items():
                            record = dict(
                                zanata_id=user_id,
                                date=day,
                                language_code=lang,
                                language=languages.get(lang) or lang,
                                translated=data['translated'],
                                approved=data['approved'],
                                module=project_id,
                                branch=version,  # todo adapt version to branch
                            )
                            yield record

    last_update += (now - last_update) // WEEK * WEEK
    LOG.info('New last update: %d', last_update)
    runtime_storage_inst.set_by_key(last_update_key, last_update)
