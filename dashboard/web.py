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
import operator
import os
import re
import urllib

import flask
from flask.ext import gravatar as gravatar_ext
from oslo.config import cfg
import time
from werkzeug import exceptions

from dashboard import memory_storage
from stackalytics.openstack.common import log as logging
from stackalytics.processor import config
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
    'marks': 'Reviews',
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
        try:
            vault = {}
            runtime_storage_inst = runtime_storage.get_runtime_storage(
                cfg.CONF.runtime_storage_uri)
            vault['runtime_storage'] = runtime_storage_inst
            vault['memory_storage'] = memory_storage.get_memory_storage(
                memory_storage.MEMORY_STORAGE_CACHED)

            init_project_types(vault)
            init_releases(vault)

            app.stackalytics_vault = vault
        except Exception as e:
            LOG.critical('Failed to initialize application: %s', e)
            LOG.exception(e)
            flask.abort(500)

    if not getattr(flask.request, 'stackalytics_updated', None):
        flask.request.stackalytics_updated = True
        memory_storage_inst = vault['memory_storage']
        have_updates = memory_storage_inst.update(
            vault['runtime_storage'].get_update(os.getpid()))

        if have_updates:
            init_project_types(vault)
            init_releases(vault)
            init_module_groups(vault)

    return vault


def get_memory_storage():
    return get_vault()['memory_storage']


def init_releases(vault):
    runtime_storage_inst = vault['runtime_storage']
    releases = runtime_storage_inst.get_by_key('releases')
    if not releases:
        raise Exception('Releases are missing in runtime storage')
    vault['start_date'] = releases[0]['end_date']
    vault['end_date'] = releases[-1]['end_date']
    start_date = releases[0]['end_date']
    for r in releases[1:]:
        r['start_date'] = start_date
        start_date = r['end_date']
    vault['releases'] = dict((r['release_name'].lower(), r)
                             for r in releases[1:])


def init_project_types(vault):
    runtime_storage_inst = vault['runtime_storage']
    project_type_options = {}
    project_type_group_index = {'all': set()}

    for repo in runtime_storage_inst.get_by_key('repos') or []:
        project_type = repo['project_type'].lower()
        project_group = None
        if ('project_group' in repo) and (repo['project_group']):
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


def init_module_groups(vault):
    runtime_storage_inst = vault['runtime_storage']
    module_index = {}
    module_id_index = {}
    module_groups = runtime_storage_inst.get_by_key('module_groups') or []

    for module_group in module_groups:
        module_group_name = module_group['module_group_name']
        module_group_id = module_group_name.lower()

        module_id_index[module_group_name] = {
            'group': True,
            'id': module_group_id,
            'text': module_group_name,
            'modules': [m.lower() for m in module_group['modules']],
        }

        modules = module_group['modules']
        for module in modules:
            if module in module_index:
                module_index[module].add(module_group_id)
            else:
                module_index[module] = set([module_group_id])

    memory_storage_inst = vault['memory_storage']
    for module in memory_storage_inst.get_modules():
        module_id_index[module] = {
            'id': module.lower(),
            'text': module,
            'modules': [module.lower()],
        }

    vault['module_group_index'] = module_index
    vault['module_id_index'] = module_id_index
    vault['module_groups'] = module_groups


def get_project_type_options():
    return get_vault()['project_type_options']


def get_release_options():
    runtime_storage_inst = get_vault()['runtime_storage']
    releases = runtime_storage_inst.get_by_key('releases')[1:]
    releases.reverse()
    return releases


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


def get_user_from_runtime_storage(user_id):
    runtime_storage_inst = get_vault()['runtime_storage']
    return utils.load_user(runtime_storage_inst, user_id)


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
        return [default] if default else []
    else:
        return []


def get_single_parameter(kwargs, singular_name, use_default=True):
    param = get_parameter(kwargs, singular_name, use_default)
    if param:
        return param[0]
    else:
        return ''


def resolve_modules(module_ids):
    module_id_index = get_vault()['module_id_index']
    modules = set()
    for module_id in module_ids:
        if module_id in module_id_index:
            modules |= set(module_id_index[module_id]['modules'])
    return modules


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
                    record_ids &= (memory_storage.get_record_ids_by_modules(
                        resolve_modules(param)))

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
                param = [u for u in param if get_user_from_runtime_storage(u)]
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

            def commit_filter(result, record, param_id):
                result[record[param_id]]['metric'] += 1

            def loc_filter(result, record, param_id):
                result[record[param_id]]['metric'] += record['loc']

            def mark_filter(result, record, param_id):
                value = record['value']
                result_by_param = result[record[param_id]]
                result_by_param['metric'] += 1

                if value in result_by_param:
                    result_by_param[value] += 1
                else:
                    result_by_param[value] = 1

            def mark_finalize(record):
                new_record = {}
                for key in ['id', 'metric', 'name']:
                    new_record[key] = record[key]

                positive = 0
                mark_distribution = []
                for key in ['-2', '-1', '1', '2']:
                    if key in record:
                        if key in ['1', '2']:
                            positive += record[key]
                        mark_distribution.append(str(record[key]))
                    else:
                        mark_distribution.append('0')

                new_record['comment'] = (
                    '|'.join(mark_distribution) +
                    ' (%.1f%%)' % ((positive * 100.0) / record['metric']))
                return new_record

            metric_param = (flask.request.args.get('metric') or
                            get_default('metric'))
            metric = metric_param.lower()
            aggregate_filter = None

            if metric == 'commits':
                metric_filter = commit_filter
            elif metric == 'loc':
                metric_filter = loc_filter
            elif metric == 'marks':
                metric_filter = mark_filter
                aggregate_filter = mark_finalize
            else:
                raise Exception('Invalid metric %s' % metric)

            kwargs['metric_filter'] = metric_filter
            kwargs['finalize_handler'] = aggregate_filter
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
                if isinstance(e, exceptions.HTTPException):
                    raise  # ignore Flask exceptions
                LOG.exception(e)
                flask.abort(404)

        return exception_handler_decorated_function

    return decorator


def make_page_title(company, user_id, module, release):
    if company:
        memory_storage = get_vault()['memory_storage']
        company = memory_storage.get_original_company_name(company)
    if company or user_id:
        if user_id:
            s = get_user_from_runtime_storage(user_id)['user_name']
            if company:
                s += ' (%s)' % company
        else:
            s = company
    else:
        s = 'OpenStack community'
    s += ' contribution'
    if module:
        s += ' to %s' % module
    if release != 'all':
        s += ' in %s release' % release.capitalize()
    else:
        s += ' in all releases'
    return s


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
                if release != 'all':
                    if release not in releases:
                        release = None
                    else:
                        release = releases[release]['release_name']
            ctx['release'] = (release or get_default('release')).lower()

            ctx['project_type_options'] = get_project_type_options()
            ctx['release_options'] = get_release_options()
            ctx['metric_options'] = sorted(METRIC_LABELS.items(),
                                           key=lambda x: x[0])

            ctx['company'] = get_single_parameter(kwargs, 'company')
            ctx['module'] = get_single_parameter(kwargs, 'module')
            ctx['user_id'] = get_single_parameter(kwargs, 'user_id')
            ctx['page_title'] = make_page_title(ctx['company'], ctx['user_id'],
                                                ctx['module'], ctx['release'])

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


def contribution_details(records):
    blueprints_map = {}
    bugs_map = {}
    companies_map = {}
    commits = []
    marks = dict((m, 0) for m in [-2, -1, 0, 1, 2])
    loc = 0

    for record in records:
        if record['record_type'] == 'commit':
            loc += record['loc']
            commit = record.copy()
            commit['branches'] = ','.join(commit['branches'])
            commits.append(commit)
            blueprint = commit['blueprint_id']
            if blueprint:
                if blueprint in blueprints_map:
                    blueprints_map[blueprint].append(commit)
                else:
                    blueprints_map[blueprint] = [commit]

            bug = commit['bug_id']
            if bug:
                if bug in bugs_map:
                    bugs_map[bug].append(commit)
                else:
                    bugs_map[bug] = [commit]

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
                  key=lambda x: int(x['id']))
    commits.sort(key=lambda x: x['date'], reverse=True)

    result = {
        'blueprints': blueprints,
        'bugs': bugs,
        'commit_count': len(commits),
        'companies': companies_map,
        'loc': loc,
        'marks': marks,
    }
    return result


# AJAX Handlers ---------

def _get_aggregated_stats(records, metric_filter, keys, param_id,
                          param_title=None, finalize_handler=None):
    param_title = param_title or param_id
    result = dict((c, {'metric': 0, 'id': c}) for c in keys)
    for record in records:
        metric_filter(result, record, param_id)
        result[record[param_id]]['name'] = record[param_title]

    if not finalize_handler:
        finalize_handler = lambda x: x

    response = [finalize_handler(result[r]) for r in result
                if result[r]['metric']]
    response.sort(key=lambda x: x['metric'], reverse=True)
    return response


@app.route('/data/companies')
@exception_handler()
@record_filter()
@aggregate_filter()
def get_companies(records, metric_filter, finalize_handler):
    response = _get_aggregated_stats(records, metric_filter,
                                     get_memory_storage().get_companies(),
                                     'company_name')
    return json.dumps(response)


@app.route('/data/modules')
@exception_handler()
@record_filter()
@aggregate_filter()
def get_modules(records, metric_filter, finalize_handler):
    response = _get_aggregated_stats(records, metric_filter,
                                     get_memory_storage().get_modules(),
                                     'module')
    return json.dumps(response)


@app.route('/data/engineers')
@exception_handler()
@record_filter()
@aggregate_filter()
def get_engineers(records, metric_filter, finalize_handler):
    response = _get_aggregated_stats(records, metric_filter,
                                     get_memory_storage().get_user_ids(),
                                     'user_id', 'author_name',
                                     finalize_handler=finalize_handler)
    return json.dumps(response)


def extend_record(record):
    record['date_str'] = format_datetime(record['date'])
    record['author_link'] = make_link(
        record['author_name'], '/',
        {'user_id': record['user_id'], 'company': ''})
    record['company_link'] = make_link(
        record['company_name'], '/',
        {'company': record['company_name'], 'user_id': ''})
    record['gravatar'] = gravatar(record['author_email'])


@app.route('/data/activity.json')
@exception_handler()
@record_filter()
def get_activity_json(records):
    start_record = int(flask.request.args.get('start_record') or 0)
    page_size = int(flask.request.args.get('page_size') or
                    DEFAULT_RECORDS_LIMIT)
    result = []
    memory_storage_inst = get_memory_storage()
    for record in records:
        if record['record_type'] == 'commit':
            commit = record.copy()
            commit['branches'] = ','.join(commit['branches'])
            if 'correction_comment' not in commit:
                commit['correction_comment'] = ''
            commit['message'] = make_commit_message(record)
            extend_record(commit)
            result.append(commit)
        elif record['record_type'] == 'mark':
            review = record.copy()
            parent = memory_storage_inst.get_record_by_primary_key(
                review['review_id'])
            if parent:
                review['subject'] = parent['subject']
                review['url'] = parent['url']
                review['parent_author_link'] = make_link(
                    parent['author_name'], '/',
                    {'user_id': parent['user_id'],
                     'company': ''})
                extend_record(review)
                result.append(review)

    result.sort(key=lambda x: x['date'], reverse=True)
    return json.dumps({'activity':
                      result[start_record:start_record + page_size]})


@app.route('/data/contribution.json')
@exception_handler()
@record_filter(ignore='metric')
def get_contribution_json(records):
    return json.dumps({'contribution': contribution_details(records)})


def _get_collection(records, collection_name, name_key, query_param=None):
    if not query_param:
        query_param = name_key
    query = flask.request.args.get(query_param) or ''
    options = set()
    for record in records:
        name = record[name_key]
        if name in options:
            continue
        if name.lower().find(query.lower()) >= 0:
            options.add(name)
    result = [{'id': safe_encode(c.lower()), 'text': c}
              for c in sorted(options)]
    return json.dumps({collection_name: result})


@app.route('/data/companies.json')
@exception_handler()
@record_filter(ignore='company')
def get_companies_json(records):
    return _get_collection(records, 'companies', 'company_name')


@app.route('/data/modules.json')
@exception_handler()
@record_filter(ignore='module')
def get_modules_json(records):
    module_group_index = get_vault()['module_group_index']
    module_id_index = get_vault()['module_id_index']

    modules_set = set()
    for record in records:
        module = record['module']
        if module not in modules_set:
            modules_set.add(module)

    modules_groups_set = set()
    for module in modules_set:
        if module in module_group_index:
            modules_groups_set |= module_group_index[module]

    modules_set |= modules_groups_set

    query = (flask.request.args.get('module_name') or '').lower()
    options = []

    for module in modules_set:
        if module.find(query) >= 0:
            options.append(module_id_index[module])

    result = sorted(options, key=operator.itemgetter('text'))
    return json.dumps({'modules': result})


@app.route('/data/companies/<company_name>.json')
def get_company(company_name):
    memory_storage = get_vault()['memory_storage']
    for company in memory_storage.get_companies():
        if company.lower() == company_name.lower():
            return json.dumps({
                'company': {
                    'id': company_name,
                    'text': memory_storage.get_original_company_name(
                company_name)}
            })
    return json.dumps({})


@app.route('/data/modules/<module>.json')
def get_module(module):
    module_id_index = get_vault()['module_id_index']
    module = module.lower()
    if module in module_id_index:
        return json.dumps({'module': module_id_index[module]})
    return json.dumps({})


@app.route('/data/users.json')
@exception_handler()
@record_filter(ignore='user_id')
def get_users_json(records):
    user_name_query = flask.request.args.get('user_name') or ''
    user_ids = set()
    result = []
    for record in records:
        user_id = record['user_id']
        if user_id in user_ids:
            continue
        user_name = record['author_name']
        if user_name.lower().find(user_name_query.lower()) >= 0:
            user_ids.add(user_id)
            result.append({'id': user_id, 'text': user_name})
    result.sort(key=lambda x: x['text'])
    return json.dumps({'users': result})


@app.route('/data/users/<user_id>.json')
def get_user(user_id):
    user = get_user_from_runtime_storage(user_id)
    if not user:
        flask.abort(404)
    user['id'] = user['user_id']
    user['text'] = user['user_name']
    if user['companies']:
        company_name = user['companies'][-1]['company_name']
        user['company_link'] = make_link(
            company_name, '/', {'company': company_name, 'user_id': ''})
    else:
        user['company_link'] = ''
    user['gravatar'] = gravatar(user['emails'][0])
    return json.dumps({'user': user})


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

    param = get_parameter(kwargs, 'metric')
    if ('reviews' in param) or ('marks' in param):
        handler = lambda record: 0
    else:
        handler = lambda record: record['loc']

    # fill stats with the data
    for record in records:
        week = record['week']
        if week in weeks:
            week_stat_loc[week] += handler(record)
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


@app.route('/data/report/commit')
@exception_handler()
@record_filter()
def get_commit_report(records):
    loc_threshold = int(flask.request.args.get('loc_threshold') or 0)
    response = []
    for record in records:
        if ('loc' in record) and (record['loc'] > loc_threshold):
            nr = dict([(k, record[k]) for k in ['loc', 'subject', 'module',
                                                'primary_key', 'change_id']])
            response.append(nr)
    return json.dumps(response, skipkeys=True, indent=2)


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
def make_link(title, uri=None, options=None):
    param_names = ('release', 'project_type', 'module', 'company', 'user_id',
                   'metric')
    param_values = {}
    for param_name in param_names:
        v = get_parameter({}, param_name, param_name)
        if v:
            param_values[param_name] = ','.join(v)
    if options:
        param_values.update(options)
    if param_values:
        uri += '?' + '&'.join(['%s=%s' % (n, safe_encode(v))
                               for n, v in param_values.iteritems()])
    return '<a href="%(uri)s">%(title)s</a>' % {'uri': uri, 'title': title}


def unwrap_text(text):
    res = ''
    for line in text.splitlines():
        s = line.rstrip()
        if not s:
            continue
        res += line
        if (not s[0].isalpha()) or (s[-1] in ['.', '!', '?', '>', ':', ';']):
            res += '\n'
        else:
            res += ' '
    return res.rstrip()


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

    s = unwrap_text(s)
    return s


gravatar = gravatar_ext.Gravatar(app, size=64, rating='g', default='wavatar')


def main():
    app.run(cfg.CONF.listen_host, cfg.CONF.listen_port)

if __name__ == '__main__':
    main()
