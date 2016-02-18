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

import flask
from oslo_config import cfg
from oslo_log import log as logging
from six.moves.urllib import parse
import time

from stackalytics.dashboard import vault


LOG = logging.getLogger(__name__)


DEFAULTS = {
    'review_nth': 5,
}

METRIC_LABELS = {
    'loc': 'Lines of code',
    'commits': 'Commits',
    'marks': 'Reviews',
    'emails': 'Emails',
    'bpd': 'Drafted Blueprints',
    'bpc': 'Completed Blueprints',
    'filed-bugs': 'Filed Bugs',
    'resolved-bugs': 'Resolved Bugs',
    'person-day': "Person-day effort",
    'ci': 'CI votes',
    'patches': 'Patch Sets',
    'translations': 'Translations',
}

METRIC_TO_RECORD_TYPE = {
    'loc': ['commit'],
    'commits': ['commit'],
    'marks': ['mark'],
    'emails': ['email'],
    'bpd': ['bpd'],
    'bpc': ['bpc'],
    'filed-bugs': ['bugf'],
    'resolved-bugs': ['bugr'],
    'members': ['member'],
    'person-day': ['mark', 'patch', 'email', 'bpd', 'bugf'],
    'ci': ['ci'],
    'patches': ['patch'],
    'translations': ['tr'],
}

FILTER_PARAMETERS = ['release', 'project_type', 'module', 'company', 'user_id',
                     'metric', 'start_date', 'end_date', 'blueprint_id',
                     'core_in']

DEFAULT_RECORDS_LIMIT = 10
DEFAULT_STATIC_ACTIVITY_SIZE = 100


def get_default(param_name):
    if 'release' not in DEFAULTS:
        release = cfg.CONF.default_release
        if not release:
            runtime_storage_inst = vault.get_runtime_storage()
            releases = runtime_storage_inst.get_by_key('releases')
            if releases:
                for r in releases:
                    if r['end_date'] > time.time():
                        release = r['release_name']
                        break
                else:
                    release = releases[-1]['release_name']
            else:
                release = 'all'
        DEFAULTS['release'] = release.lower()
        DEFAULTS['metric'] = cfg.CONF.default_metric.lower()
        DEFAULTS['project_type'] = cfg.CONF.default_project_type.lower()

    if param_name in DEFAULTS:
        return DEFAULTS[param_name]
    else:
        return None


def get_parameter(kwargs, name, plural_name=None, use_default=True):
    processed_params = kwargs.get('_params') or {}
    if name in processed_params:
        return processed_params[name]

    if name in kwargs:
        p = kwargs[name]
    else:
        p = flask.request.args.get(name)
        if (not p) and plural_name:
            p = flask.request.args.get(plural_name)
    if p:
        return parse.unquote_plus(p).split(',')
    elif use_default:
        default = get_default(name)
        return [default] if default else []
    else:
        return []


def get_single_parameter(kwargs, name, use_default=True):
    param = get_parameter(kwargs, name, use_default)
    if param:
        return param[0]
    else:
        return None
