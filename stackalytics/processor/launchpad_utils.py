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

from oslo_log import log as logging
import requests
import six

from stackalytics.processor import utils


LOG = logging.getLogger(__name__)

BUG_STATUSES = ['New', 'Incomplete', 'Opinion', 'Invalid', 'Won\'t Fix',
                'Expired', 'Confirmed', 'Triaged', 'In Progress',
                'Fix Committed', 'Fix Released',
                'Incomplete (with response)',
                'Incomplete (without response)']
LP_URI_V1 = 'https://api.launchpad.net/1.0/%s'
LP_URI_DEVEL = 'https://api.launchpad.net/devel/%s'

launchpad_session = requests.Session()


def link_to_launchpad_id(link):
    return link[link.find('~') + 1:]


def _lp_profile_by_launchpad_id(launchpad_id):
    LOG.debug('Lookup user id %s at Launchpad', launchpad_id)
    uri = LP_URI_V1 % ('~' + launchpad_id)
    lp_profile = utils.read_json_from_uri(uri, session=launchpad_session)
    utils.validate_lp_display_name(lp_profile)
    return lp_profile


def query_lp_user_name(launchpad_id):
    """Query user name by Launchpad ID

    :param launchpad_id: user's launchpad id
    :return: user name
    """
    if not launchpad_id:
        return None

    lp_profile = _lp_profile_by_launchpad_id(launchpad_id)

    if not lp_profile:
        LOG.debug('User with id %s not found', launchpad_id)
        return launchpad_id

    return lp_profile['display_name']


def _lp_profile_by_email(email):
    LOG.debug('Lookup user email %s at Launchpad', email)
    uri = LP_URI_V1 % ('people/?ws.op=getByEmail&email=' + email)
    lp_profile = utils.read_json_from_uri(uri, session=launchpad_session)
    utils.validate_lp_display_name(lp_profile)
    return lp_profile


def query_lp_info(email):
    """Query Launchpad ID and user name by email

    :param email: user email
    :return: tuple (launchpad id, name)
    """
    lp_profile = None
    if not utils.check_email_validity(email):
        LOG.debug('User email is not valid %s', email)
    else:
        lp_profile = _lp_profile_by_email(email)

    if not lp_profile:
        LOG.debug('User with email %s not found', email)
        return None, None

    LOG.debug('Email %(email)s is mapped to launchpad user %(lp)s',
              {'email': email, 'lp': lp_profile['name']})
    return lp_profile['name'], lp_profile['display_name']


def lp_module_exists(module):
    uri = LP_URI_DEVEL % module
    request = utils.do_request(uri)

    LOG.debug('Checked uri: %(uri)s, status: %(status)s',
              {'uri': uri, 'status': request.status_code})
    return request.status_code != 404


def lp_blueprint_generator(module):
    uri = LP_URI_DEVEL % (module + '/all_specifications')
    while uri:
        LOG.debug('Reading chunk from uri %s', uri)
        chunk = utils.read_json_from_uri(uri, session=launchpad_session)

        if not chunk:
            LOG.warning('No data was read from uri %s', uri)
            break

        for record in chunk['entries']:
            yield record

        uri = chunk.get('next_collection_link')


def lp_bug_generator(module, modified_since):
    uri = LP_URI_DEVEL % (module + '?ws.op=searchTasks')
    for status in BUG_STATUSES:
        uri += '&status=' + six.moves.urllib.parse.quote_plus(status)
    if modified_since:
        uri += '&modified_since=' + utils.timestamp_to_utc_date(modified_since)

    while uri:
        LOG.debug('Reading chunk from uri %s', uri)
        chunk = utils.read_json_from_uri(uri, session=launchpad_session)

        if not chunk:
            LOG.warning('No data was read from uri %s', uri)
            break

        for record in chunk['entries']:
            yield record

            related_tasks_uri = record['related_tasks_collection_link']
            LOG.debug('Reading related task from uri %s', related_tasks_uri)
            related_tasks = utils.read_json_from_uri(related_tasks_uri,
                                                     session=launchpad_session)
            if not related_tasks:
                LOG.warning('No data was read from uri %s', uri)
            elif related_tasks['entries']:
                for related_task in related_tasks['entries']:
                    yield related_task

        uri = chunk.get('next_collection_link')
