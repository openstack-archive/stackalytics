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

from oslo.config import cfg


OPTS = [
    cfg.StrOpt('default-data-uri',
               default='https://raw.github.com/stackforge/stackalytics/'
                       'master/etc/default_data.json',
               help='URI for default data'),
    cfg.StrOpt('sources-root', default='/var/local/stackalytics',
               help='The folder that holds all project sources to analyze'),
    cfg.StrOpt('runtime-storage-uri', default='memcached://127.0.0.1:11211',
               help='Storage URI'),
    cfg.StrOpt('listen-host', default='127.0.0.1',
               help='The address dashboard listens on'),
    cfg.IntOpt('listen-port', default=8080,
               help='The port dashboard listens on'),
    cfg.IntOpt('days_to_update_members', default=7,
               help='Number of days to update members'),
    cfg.StrOpt('corrections-uri',
               default=('https://raw.github.com/stackforge/stackalytics/'
                        'master/etc/corrections.json'),
               help='The address of file with corrections data'),
    cfg.StrOpt('review-uri', default='gerrit://review.openstack.org',
               help='URI of review system'),
    cfg.StrOpt('ssh-key-filename', default='/home/user/.ssh/id_rsa',
               help='SSH key for gerrit review system access'),
    cfg.StrOpt('ssh-username', default='user',
               help='SSH username for gerrit review system access'),
    cfg.BoolOpt('force-update', default=False,
                help='Forcibly read default data and update records'),
    cfg.StrOpt('program-list-uri',
               default=('https://raw.github.com/openstack/governance/'
                        'master/reference/programs.yaml'),
               help='The address of file with list of programs'),
    cfg.StrOpt('default-metric', default='marks',
               help='Default metric'),
    cfg.StrOpt('default-release',
               help='Default release, the most recent if not set'),
    cfg.StrOpt('default-project-type', default='openstack',
               help='Default project type'),
]
