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

import copy

from oslo_config import cfg


CONNECTION_OPTS = [
    cfg.StrOpt('runtime-storage-uri', default='memcached://127.0.0.1:11211',
               help='Storage URI'),
]

PROCESSOR_OPTS = [
    cfg.StrOpt('default-data-uri',
               default='https://git.openstack.org/cgit/'
                       'openstack/stackalytics/plain/etc/default_data.json',
               help='URI for default data. A local file can be used with the '
                    'prefix "file://". For example, '
                    'default_data_uri = file:///path/to/default_data.json'),
    cfg.StrOpt('sources-root', default='/var/local/stackalytics',
               help='The folder that holds all project sources to analyze'),
    cfg.IntOpt('days_to_update_members', default=30,
               help='Number of days to update members'),
    cfg.StrOpt('corrections-uri',
               default=('https://git.openstack.org/cgit/'
                        'openstack/stackalytics/plain/etc/corrections.json'),
               help='The address of file with corrections data'),
    cfg.StrOpt('review-uri', default='gerrit://review.openstack.org',
               help='URI of review system'),
    cfg.StrOpt('git-base-uri', default='git://git.openstack.org',
               help='git base location'),
    cfg.StrOpt('ssh-key-filename', default='/home/user/.ssh/id_rsa',
               help='SSH key for gerrit review system access'),
    cfg.StrOpt('ssh-username', default='user',
               help='SSH username for gerrit review system access'),
    cfg.StrOpt('translation-team-uri',
               default='https://git.openstack.org/cgit/openstack/i18n/'
                       'plain/tools/zanata/translation_team.yaml',
               help='URI of translation team data'),
    cfg.StrOpt("fetching-user-source", default='launchpad',
               choices=['launchpad', '<None>'],
               help="Source for fetching user profiles"),
    cfg.IntOpt('members-look-ahead', default=250,
               help='How many member profiles to look ahead after the last'),
    cfg.IntOpt('read-timeout', default=120,
               help='Number of seconds to wait for remote response'),
    cfg.IntOpt('gerrit-retry', default=10,
               help='How many times to retry after Gerrit errors'),
]


def list_opts():
    yield (None, copy.deepcopy(CONNECTION_OPTS + PROCESSOR_OPTS))
