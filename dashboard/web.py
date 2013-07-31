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

import cgi
import datetime
import functools
import json
import os
import re
import urllib

import flask
from flask.ext import gravatar as gravatar_ext
from oslo.config import cfg
import time

from dashboard import memory_storage
from stackalytics.openstack.common import log as logging
from stackalytics.processor import config
from stackalytics.processor import persistent_storage
from stackalytics.processor import runtime_storage
from stackalytics.processor import utils


# Constants and Parameters ---------

DEFAULTS = {
    'metric': 'commits',
    'release': 'havana',
    'project_type': 'openstack',
}

METRIC_LABELS = {
    'loc': 'Lines of code',
    'commits': 'Commits',
    'reviews': 'Reviews',
    'marks': 'Marks',
}

DEFAULT_RECORDS_LIMIT = 10


# Application objects ---------

app = flask.Flask(__name__)
app.config.from_object(__name__)
app.config.from_envvar('DASHBOARD_CONF', silent=True)

LOG = logging.getLogger(__name__)

conf = cfg.CONF
conf.register_opts(config.OPTS)
logging.setup('dashboard')
LOG.info('Logging enabled')

conf_file = os.getenv('STACKALYTICS_CONF')
if conf_file and os.path.isfile(conf_file):
    conf(default_config_files=[conf_file])
    app.config['DEBUG'] = cfg.CONF.debug
else:
    LOG.warn('Conf file is empty or not exist')


def get_vault():
    vault = getattr(app, 'stackalytics_vault', None)
    if not vault:
        vault = {}
        vault['runtime_storage'] = runtime_storage.get_runtime_storage(
            cfg.CONF.runtime_storage_uri)
        vault['persistent_storage'] = (
            persistent_storage.get_persistent_storage(
                cfg.CONF.persistent_storage_uri))
        vault['memory_storage'] = memory_storage.get_memory_storage(
            memory_storage.MEMORY_STORAGE_CACHED,
            vault['runtime_storage'].get_update(os.getpid()))

        persistent_storage_inst = vault['persistent_storage']
        releases = list(persistent_storage_inst.find('releases'))
        vault['start_date'] = releases[0]['end_date']
        vault['end_date'] = releases[-1]['end_date']
        start_date = releases[0]['end_date']
        for r in releases[1:]:
            r['start_date'] = start_date
            start_date = r['end_date']
        vault['releases'] = dict((r['release_name'].lower(), r)
                                 for r in releases[1:])
        modules = persistent_storage_inst.find('repos')
        vault['modules'] = dict((r['module'].lower(),
                                 r['project_type'].lower()) for r in modules)
        app.stackalytics_vault = vault

        init_project_types(vault)
    else:
        if not getattr(flask.request, 'stackalytics_updated', None):
            flask.request.stackalytics_updated = True
            memory_storage_inst = vault['memory_storage']
            memory_storage_inst.update(
                vault['runtime_storage'].get_update(os.getpid()))

    return vault


def get_memory_storage():
    return get_vault()['memory_storage']


def init_project_types(vault):
    persistent_storage_inst = vault['persistent_storage']
    project_type_options = {}
    project_type_group_index = {'all': set()}

    for repo in persistent_storage_inst.find('repos'):
        project_type = repo['project_type'].lower()
        project_group = None
        if 'project_group' in repo:
            project_group = repo['project_group'].lower()

        if project_type in project_type_options:
            if project_group:
                project_type_options[project_type].add(project_group)
        else:
            if project_group:
                project_type_options[project_type] = set([project_group])
            else:
                project_type_options[project_type] = set()

        module = repo['module']
        if project_type in project_type_group_index:
            project_type_group_index[project_type].add(module)
        else:
            project_type_group_index[project_type] = set([module])

        if project_group:
            if project_group in project_type_group_index:
                project_type_group_index[project_group].add(module)
            else:
                project_type_group_index[project_group] = set([module])

        project_type_group_index['all'].add(module)

    vault['project_type_options'] = project_type_options
    vault['project_type_group_index'] = project_type_group_index


def get_project_type_options():
    return get_vault()['project_type_options']


def is_project_type_valid(project_type):
    if not project_type:
        return False
    project_type = project_type.lower()
    if project_type == 'all':
        return True
    project_types = get_project_type_options()
    if project_type in project_types:
        return True
    for p, g in project_types.iteritems():
        if project_type in g:
            return True
    return False


# Utils ---------

def get_default(param_name):
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
            flask.request.args.get(plural_name)
    if p:
        return p.split(',')
    elif use_default:
        default = get_default(singular_name)
        return [default] if default else None
    else:
        return []


# Decorators ---------

def record_filter(ignore=None, use_default=True):
    if not ignore:
        ignore = []

    def decorator(f):
        @functools.wraps(f)
        def record_filter_decorated_function(*args, **kwargs):

            vault = get_vault()
            memory_storage = vault['memory_storage']
            record_ids = set(memory_storage.get_record_ids())  # make a copy

            if 'module' not in ignore:
                param = get_parameter(kwargs, 'module', 'modules', use_default)
                if param:
                    record_ids &= (
                        memory_storage.get_record_ids_by_modules(param))

            if 'project_type' not in ignore:
                param = get_parameter(kwargs, 'project_type', 'project_types',
                                      use_default)
                if param:
                    ptgi = vault['project_type_group_index']
                    modules = set()
                    for project_type in param:
                        project_type = project_type.lower()
                        if project_type in ptgi:
                            modules |= ptgi[project_type]
                    record_ids &= (
                        memory_storage.get_record_ids_by_modules(modules))

            if 'user_id' not in ignore:
                param = get_parameter(kwargs, 'user_id', 'user_ids')
                if param:
                    record_ids &= (
                        memory_storage.get_record_ids_by_user_ids(param))

            if 'company' not in ignore:
                param = get_parameter(kwargs, 'company', 'companies')
                if param:
                    record_ids &= (
                        memory_storage.get_record_ids_by_companies(param))

            if 'release' not in ignore:
                param = get_parameter(kwargs, 'release', 'releases',
                                      use_default)
                if param:
                    if 'all' not in param:
                        record_ids &= (
                            memory_storage.get_record_ids_by_releases(
                                c.lower() for c in param))

            if 'metric' not in ignore:
                param = get_parameter(kwargs, 'metric')
                if 'reviews' in param:
                    record_ids &= memory_storage.get_review_ids()
                elif 'marks' in param:
                    record_ids &= memory_storage.get_mark_ids()
                elif ('loc' in param) or ('commits' in param):
                    record_ids &= memory_storage.get_commit_ids()

            kwargs['records'] = memory_storage.get_records(record_ids)
            return f(*args, **kwargs)

        return record_filter_decorated_function

    return decorator


def aggregate_filter():
    def decorator(f):
        @functools.wraps(f)
        def aggregate_filter_decorated_function(*args, **kwargs):

            metric_param = (flask.request.args.get('metric') or
                            get_default('metric'))
            metric = metric_param.lower()
            if metric in ['commits', 'reviews', 'marks']:
                metric_filter = lambda r: 1
            elif metric == 'loc':
                metric_filter = lambda r: r['loc']
            else:
                raise Exception('Invalid metric %s' % metric)

            kwargs['metric_filter'] = metric_filter
            return f(*args, **kwargs)

        return aggregate_filter_decorated_function

    return decorator


def exception_handler():
    def decorator(f):
        @functools.wraps(f)
        def exception_handler_decorated_function(*args, **kwargs):
            try:
                return f(*args, **kwargs)
            except Exception as e:
                LOG.error(e)
                flask.abort(404)

        return exception_handler_decorated_function

    return decorator


def templated(template=None, return_code=200):
    def decorator(f):
        @functools.wraps(f)
        def templated_decorated_function(*args, **kwargs):

            vault = get_vault()
            template_name = template
            if template_name is None:
                template_name = (flask.request.endpoint.replace('.', '/') +
                                 '.html')
            ctx = f(*args, **kwargs)
            if ctx is None:
                ctx = {}

            # put parameters into template
            metric = flask.request.args.get('metric')
            if metric not in METRIC_LABELS:
                metric = None
            ctx['metric'] = metric or get_default('metric')
            ctx['metric_label'] = METRIC_LABELS[ctx['metric']]

            project_type = flask.request.args.get('project_type')
            if not is_project_type_valid(project_type):
                project_type = get_default('project_type')
            ctx['project_type'] = project_type

            release = flask.request.args.get('release')
            releases = vault['releases']
            if release:
                release = release.lower()
                if release not in releases:
                    release = None
                else:
                    release = releases[release]['release_name']
            ctx['release'] = (release or get_default('release')).lower()

            ctx['project_type_options'] = get_project_type_options()

            return flask.render_template(template_name, **ctx), return_code

        return templated_decorated_function

    return decorator


# Handlers ---------

@app.route('/')
@templated()
def overview():
    pass


@app.errorhandler(404)
@templated('404.html', 404)
def page_not_found(e):
    pass


def contribution_details(records, limit=DEFAULT_RECORDS_LIMIT):
    blueprints_map = {}
    bugs_map = {}
    companies_map = {}
    commits = []
    marks = dict((m, 0) for m in [-2, -1, 0, 1, 2])
    loc = 0

    for record in records:
        if record['record_type'] == 'commit':
            loc += record['loc']
            commits.append(record)
            blueprint = record['blueprint_id']
            if blueprint:
                if blueprint in blueprints_map:
                    blueprints_map[blueprint].append(record)
                else:
                    blueprints_map[blueprint] = [record]

            bug = record['bug_id']
            if bug:
                if bug in bugs_map:
                    bugs_map[bug].append(record)
                else:
                    bugs_map[bug] = [record]

            company = record['company_name']
            if company:
                if company in companies_map:
                    companies_map[company]['loc'] += record['loc']
                    companies_map[company]['commits'] += 1
                else:
                    companies_map[company] = {'loc': record['loc'],
                                              'commits': 1}
        elif record['record_type'] == 'mark':
            marks[int(record['value'])] += 1

    blueprints = sorted([{'id': key,
                          'module': value[0]['module'],
                          'records': value}
                         for key, value in blueprints_map.iteritems()],
                        key=lambda x: x['id'])
    bugs = sorted([{'id': key, 'records': value}
                   for key, value in bugs_map.iteritems()],
                  key=lambda x: x['id'])
    commits.sort(key=lambda x: x['date'], reverse=True)

    result = {
        'blueprints': blueprints,
        'bugs': bugs,
        'commits': commits[0:limit],
        'commit_count': len(commits),
        'companies': companies_map,
        'loc': loc,
        'marks': marks,
    }
    return result


@app.route('/companies/<company>')
@exception_handler()
@templated()
@record_filter()
def company_details(company, records):
    details = contribution_details(records)
    details['company'] = (
        get_memory_storage().get_original_company_name(company))
    return details


@app.route('/modules/<module>')
@exception_handler()
@templated()
@record_filter()
def module_details(module, records):
    details = contribution_details(records)
    details['module'] = module
    return details


@app.route('/engineers/<user_id>')
@exception_handler()
@templated()
@record_filter(ignore='metric')
def engineer_details(user_id, records):
    persistent_storage = get_vault()['persistent_storage']
    user = list(persistent_storage.find('users', user_id=user_id))[0]

    details = contribution_details(records)
    details['user'] = user
    return details


# AJAX Handlers ---------

def _get_aggregated_stats(records, metric_filter, keys, param_id,
                          param_title=None):
    param_title = param_title or param_id
    result = dict((c, 0) for c in keys)
    titles = {}
    for record in records:
        result[record[param_id]] += metric_filter(record)
        titles[record[param_id]] = record[param_title]

    response = [{'id': r, 'metric': result[r], 'name': titles[r]}
                for r in result if result[r]]
    response.sort(key=lambda x: x['metric'], reverse=True)
    return response


@app.route('/data/companies')
@exception_handler()
@record_filter()
@aggregate_filter()
def get_companies(records, metric_filter):
    response = _get_aggregated_stats(records, metric_filter,
                                     get_memory_storage().get_companies(),
                                     'company_name')
    return json.dumps(response)


@app.route('/data/modules')
@exception_handler()
@record_filter()
@aggregate_filter()
def get_modules(records, metric_filter):
    response = _get_aggregated_stats(records, metric_filter,
                                     get_memory_storage().get_modules(),
                                     'module')
    return json.dumps(response)


@app.route('/data/engineers')
@exception_handler()
@record_filter()
@aggregate_filter()
def get_engineers(records, metric_filter):
    response = _get_aggregated_stats(records, metric_filter,
                                     get_memory_storage().get_user_ids(),
                                     'user_id', 'author_name')
    return json.dumps(response)


@app.route('/data/timeline')
@exception_handler()
@record_filter(ignore='release')
def timeline(records, **kwargs):
    # find start and end dates
    release_names = get_parameter(kwargs, 'release', 'releases')
    releases = get_vault()['releases']
    if not release_names:
        flask.abort(404)

    if 'all' in release_names:
        start_date = release_start_date = utils.timestamp_to_week(
            get_vault()['start_date'])
        end_date = release_end_date = utils.timestamp_to_week(
            get_vault()['end_date'])
    else:
        release = releases[release_names[0]]
        start_date = release_start_date = utils.timestamp_to_week(
            release['start_date'])
        end_date = release_end_date = utils.timestamp_to_week(
            release['end_date'])

    now = utils.timestamp_to_week(int(time.time()))

    # expand start-end to year if needed
    if release_end_date - release_start_date < 52:
        expansion = (52 - (release_end_date - release_start_date)) // 2
        if release_end_date + expansion < now:
            end_date += expansion
        else:
            end_date = now
        start_date = end_date - 52

    # empty stats for all weeks in range
    weeks = range(start_date, end_date)
    week_stat_loc = dict((c, 0) for c in weeks)
    week_stat_commits = dict((c, 0) for c in weeks)
    week_stat_commits_hl = dict((c, 0) for c in weeks)

    # fill stats with the data
    for record in records:
        week = record['week']
        if week in weeks:
            week_stat_loc[week] += record['loc']
            week_stat_commits[week] += 1
            if 'all' in release_names or record['release'] in release_names:
                week_stat_commits_hl[week] += 1

    # form arrays in format acceptable to timeline plugin
    array_loc = []
    array_commits = []
    array_commits_hl = []

    for week in weeks:
        week_str = utils.week_to_date(week)
        array_loc.append([week_str, week_stat_loc[week]])
        array_commits.append([week_str, week_stat_commits[week]])
        array_commits_hl.append([week_str, week_stat_commits_hl[week]])

    return json.dumps([array_commits, array_commits_hl, array_loc])


# Jinja Filters ---------

@app.template_filter('datetimeformat')
def format_datetime(timestamp):
    return datetime.datetime.utcfromtimestamp(
        timestamp).strftime('%d %b %Y @ %H:%M')


@app.template_filter('launchpadmodule')
def format_launchpad_module_link(module):
    return '<a href="https://launchpad.net/%s">%s</a>' % (module, module)


@app.template_filter('encode')
def safe_encode(s):
    return urllib.quote_plus(s.encode('utf-8'))


@app.template_filter('link')
def make_link(title, uri=None):
    param_names = ('release', 'metric', 'project_type')
    param_values = {}
    for param_name in param_names:
        v = get_parameter({}, param_name, param_name)
        if v:
            param_values[param_name] = ','.join(v)
    if param_values:
        uri += '?' + '&'.join(['%s=%s' % (n, v)
                               for n, v in param_values.iteritems()])
    return '<a href="%(uri)s">%(title)s</a>' % {'uri': uri, 'title': title}


@app.template_filter('commit_message')
def make_commit_message(record):
    s = record['message']
    module = record['module']

    # clear text
    s = cgi.escape(re.sub(re.compile('\n{2,}', flags=re.MULTILINE), '\n', s))

    # insert links
    s = re.sub(re.compile('(blueprint\s+)([\w-]+)', flags=re.IGNORECASE),
               r'\1<a href="https://blueprints.launchpad.net/' +
               module + r'/+spec/\2">\2</a>', s)
    s = re.sub(re.compile('(bug\s+)#?([\d]{5,7})', flags=re.IGNORECASE),
               r'\1<a href="https://bugs.launchpad.net/bugs/\2">\2</a>', s)
    s = re.sub(r'\s+(I[0-9a-f]{40})',
               r' <a href="https://review.openstack.org/#q,\1,n,z">\1</a>', s)
    return s


gravatar = gravatar_ext.Gravatar(app, size=100, rating='g',
                                 default='wavatar')


def main():
    app.run(cfg.CONF.listen_host, cfg.CONF.listen_port)

if __name__ == '__main__':
    main()
