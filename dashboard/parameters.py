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
from oslo.config import cfg
from six.moves.urllib import parse

from dashboard import vault
from stackalytics.openstack.common import log as logging


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
    'man-days': "Man-days effort"
}

METRIC_TO_RECORD_TYPE = {
    'loc': 'commit',
    'commits': 'commit',
    'marks': 'mark',
    'emails': 'email',
    'bpd': 'bpd',
    'bpc': 'bpc',
    'members': 'member',
}

DEFAULT_RECORDS_LIMIT = 10
DEFAULT_STATIC_ACTIVITY_SIZE = 100


def get_default(param_name):
    if 'release' not in DEFAULTS:
        release = cfg.CONF.default_release
        if not release:
            runtime_storage_inst = vault.get_vault()['runtime_storage']
            releases = runtime_storage_inst.get_by_key('releases')
            if releases:
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


def get_parameter(kwargs, singular_name, plural_name=None, use_default=True):
    if singular_name in kwargs:
        p = kwargs[singular_name]
    else:
        p = flask.request.args.get(singular_name)
        if (not p) and plural_name:
            p = flask.request.args.get(plural_name)
    if p:
        return parse.unquote_plus(p).split(',')
    elif use_default:
        default = get_default(singular_name)
        return [default] if default else []
    else:
        return []


def get_single_parameter(kwargs, singular_name, use_default=True):
    param = get_parameter(kwargs, singular_name, use_default)
    if param:
        return param[0]
    else:
        return ''
