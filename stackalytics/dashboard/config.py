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


DASHBOARD_OPTS = [
    cfg.HostAddressOpt('listen-host', default='127.0.0.1',
                       help='The address dashboard listens on'),
    cfg.IntOpt('listen-port', default=8080,
               help='The port dashboard listens on'),
    cfg.StrOpt('default-metric', default='marks',
               help='Default metric'),
    cfg.StrOpt('default-release',
               help='Default release, the most recent if not set'),
    cfg.StrOpt('default-project-type', default='openstack',
               help='Default project type'),
    cfg.IntOpt('dashboard-update-interval', default=3600,
               help='The interval specifies how frequently dashboard should '
                    'check for updates in seconds'),
    cfg.StrOpt('collect-profiler-stats',
               help='Name of file to store python profiler data'),
    cfg.IntOpt('age-warn', default=2 * 24 * 60 * 60,
               help='Warn if the age of data is more than this value, sec'),
]


def list_opts():
    yield (None, copy.deepcopy(DASHBOARD_OPTS))
