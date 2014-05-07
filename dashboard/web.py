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

import collections
import operator
import os
import re
import time

import flask
from flask.ext import gravatar as gravatar_ext
from oslo.config import cfg
import six

from dashboard import decorators
from dashboard import helpers
from dashboard import kpi
from dashboard import parameters
from dashboard import reports
from dashboard import vault
from stackalytics.openstack.common import log as logging
from stackalytics.processor import config
from stackalytics.processor import utils


# Application objects ---------

app = flask.Flask(__name__)
app.config.from_object(__name__)
app.config.from_envvar('DASHBOARD_CONF', silent=True)
app.register_blueprint(reports.blueprint)
app.register_blueprint(kpi.blueprint)

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
    LOG.info('Conf file is empty or not exist')


# Handlers ---------

@app.route('/')
@decorators.templated()
def overview():
    pass


@app.route('/widget')
def widget():
    return flask.render_template('widget.html')


@app.errorhandler(404)
@decorators.templated('404.html', 404)
def page_not_found(e):
    pass


# AJAX Handlers ---------

def _get_aggregated_stats(records, metric_filter, keys, param_id,
                          param_title=None, finalize_handler=None):
    param_title = param_title or param_id
    result = dict((c, {'metric': 0, 'id': c}) for c in keys)
    for record in records:
        metric_filter(result, record, param_id)
        result[record[param_id]]['name'] = record[param_title]

    response = [r for r in result.values() if r['metric']]
    response = [item for item in map(finalize_handler, response) if item]
    response.sort(key=lambda x: x['metric'], reverse=True)
    utils.add_index(response, item_filter=lambda x: x['id'] != '*independent')
    return response


@app.route('/api/1.0/new_companies')
@decorators.jsonify('stats')
@decorators.exception_handler()
@decorators.record_filter(ignore='start_date')
def get_new_companies(records, **kwargs):

    days = int(flask.request.args.get('days') or reports.DEFAULT_DAYS_COUNT)
    start_date = int(time.time()) - days * 24 * 60 * 60

    result = {}
    for record in records:
        company_name = record['company_name']
        date = record['date']

        if company_name not in result or result[company_name] > date:
            result[company_name] = date

    response = list(({'name': company_name,
                      'date': result[company_name],
                      'date_str': helpers.format_date(result[company_name])})
                    for company_name in result
                    if result[company_name] >= start_date)

    response.sort(key=lambda x: x['date'], reverse=True)
    utils.add_index(response)

    return response


@app.route('/api/1.0/stats/companies')
@decorators.jsonify('stats')
@decorators.exception_handler()
@decorators.record_filter()
@decorators.aggregate_filter()
def get_companies(records, metric_filter, finalize_handler, **kwargs):
    return _get_aggregated_stats(records, metric_filter,
                                 vault.get_memory_storage().get_companies(),
                                 'company_name',
                                 finalize_handler=finalize_handler)


@app.route('/api/1.0/stats/modules')
@decorators.jsonify('stats')
@decorators.exception_handler()
@decorators.record_filter()
@decorators.aggregate_filter()
def get_modules(records, metric_filter, finalize_handler, **kwargs):
    return _get_aggregated_stats(records, metric_filter,
                                 vault.get_memory_storage().get_modules(),
                                 'module', finalize_handler=finalize_handler)


def get_core_engineer_branch(user, modules):
    is_core = None
    for (module, branch) in (user.get('core') or []):
        if module in modules:
            is_core = branch
            if branch == 'master':  # master is preferable, but stables are ok
                break
    return is_core


@app.route('/api/1.0/stats/engineers')
@decorators.jsonify('stats')
@decorators.exception_handler()
@decorators.record_filter()
@decorators.aggregate_filter()
def get_engineers(records, metric_filter, finalize_handler, **kwargs):

    modules_names = parameters.get_parameter({}, 'module', 'modules')
    modules = set([m for m, r in vault.resolve_modules(modules_names, [''])])

    def postprocessing(record):
        if finalize_handler:
            record = finalize_handler(record)
        user = vault.get_user_from_runtime_storage(record['id'])
        record['core'] = get_core_engineer_branch(user, modules)
        return record

    return _get_aggregated_stats(records, metric_filter,
                                 vault.get_memory_storage().get_user_ids(),
                                 'user_id', 'author_name',
                                 finalize_handler=postprocessing)


@app.route('/api/1.0/stats/engineers_extended')
@decorators.jsonify('stats')
@decorators.exception_handler()
@decorators.record_filter(ignore='metric')
def get_engineers_extended(records, **kwargs):
    modules_names = parameters.get_parameter({}, 'module', 'modules')
    modules = set([m for m, r in vault.resolve_modules(modules_names, [''])])

    def postprocessing(record):
        record = decorators.mark_finalize(record)

        if not (record['mark'] or record['review'] or record['commit'] or
                record['email'] or record['patch']):
            return

        user = vault.get_user_from_runtime_storage(record['id'])
        record['company'] = user['companies'][-1]['company_name']
        record['core'] = get_core_engineer_branch(user, modules)
        return record

    def record_processing(result, record, param_id):
        result_row = result[record[param_id]]
        record_type = record['record_type']
        result_row[record_type] = result_row.get(record_type, 0) + 1
        if record_type == 'mark':
            decorators.mark_filter(result, record, param_id)

    result = {}
    for record in records:
        user_id = record['user_id']
        if user_id not in result:
            result[user_id] = {'id': user_id, 'mark': 0, 'review': 0,
                               'commit': 0, 'email': 0, 'patch': 0,
                               'metric': 0}
        record_processing(result, record, 'user_id')
        result[user_id]['name'] = record['author_name']

    response = result.values()
    response = [item for item in map(postprocessing, response) if item]
    response.sort(key=lambda x: x['metric'], reverse=True)
    utils.add_index(response)

    return response


@app.route('/api/1.0/stats/distinct_engineers')
@decorators.jsonify('stats')
@decorators.exception_handler()
@decorators.record_filter()
def get_distinct_engineers(records, **kwargs):
    result = {}
    for record in records:
        result[record['user_id']] = {
            'author_name': record['author_name'],
            'author_email': record['author_email'],
        }
    return result


@app.route('/api/1.0/activity')
@decorators.jsonify('activity')
@decorators.exception_handler()
@decorators.record_filter()
def get_activity_json(records, **kwargs):
    start_record = int(flask.request.args.get('start_record') or 0)
    page_size = int(flask.request.args.get('page_size') or
                    parameters.DEFAULT_RECORDS_LIMIT)
    query_message = flask.request.args.get('query_message')
    return helpers.get_activity(records, start_record, page_size,
                                query_message)


@app.route('/api/1.0/contribution')
@decorators.jsonify('contribution')
@decorators.exception_handler()
@decorators.record_filter(ignore='metric')
def get_contribution_json(records, **kwargs):
    return helpers.get_contribution_summary(records)


@app.route('/api/1.0/companies')
@decorators.jsonify('companies')
@decorators.exception_handler()
@decorators.record_filter(ignore='company')
@decorators.query_filter(query_param='company_name')
def get_companies_json(record_ids, query_filter, **kwargs):
    memory_storage = vault.get_memory_storage()
    companies = memory_storage.get_index_keys_by_record_ids(
        'company_name', record_ids)

    result = []
    for company in companies:
        if query_filter(company):
            result.append(memory_storage.get_original_company_name(company))

    return [{'id': utils.safe_encode(c.lower()), 'text': c}
            for c in sorted(result)]


@app.route('/api/1.0/modules')
@decorators.jsonify('modules')
@decorators.exception_handler()
@decorators.record_filter(ignore='module')
@decorators.query_filter(query_param='query')
def get_modules_json(record_ids, query_filter, **kwargs):
    module_id_index = vault.get_vault()['module_id_index']

    tags = parameters.get_parameter({}, 'tag', 'tags')

    # all modules mentioned in records
    module_ids = vault.get_memory_storage().get_index_keys_by_record_ids(
        'module', record_ids)

    add_modules = set([])
    for module in six.itervalues(module_id_index):
        if set(module['modules']) <= module_ids:
            add_modules.add(module['id'])
    module_ids |= add_modules

    # keep only modules with specified tags
    if tags:
        module_ids = set(module_id for module_id in module_ids
                         if module_id_index[module_id].get('tag') in tags)

    result = []
    for module_id in module_ids:
        module = module_id_index[module_id]
        if query_filter(module['module_group_name']):
            result.append({'id': module['id'],
                           'text': module['module_group_name'],
                           'tag': module['tag']})

    return sorted(result, key=operator.itemgetter('text'))


@app.route('/api/1.0/companies/<company_name>')
@decorators.jsonify('company')
def get_company(company_name):
    memory_storage_inst = vault.get_memory_storage()
    for company in memory_storage_inst.get_companies():
        if company.lower() == company_name.lower():
            return {
                'id': company_name,
                'text': memory_storage_inst.get_original_company_name(
                    company_name)
            }
    flask.abort(404)


@app.route('/api/1.0/modules/<module>')
@decorators.jsonify('module')
def get_module(module):
    module_id_index = vault.get_vault()['module_id_index']
    module = module.lower()
    if module in module_id_index:
        return {'id': module_id_index[module]['id'],
                'text': module_id_index[module]['module_group_name'],
                'tag': module_id_index[module]['tag']}
    flask.abort(404)


@app.route('/api/1.0/members')
@decorators.jsonify('members')
@decorators.exception_handler()
@decorators.record_filter(ignore=['release', 'project_type', 'module'])
def get_members(records, **kwargs):
    response = []
    for record in records:
        record = vault.extend_record(record)
        nr = dict([(k, record[k]) for k in
                   ['author_name', 'date', 'company_name', 'member_uri']])
        nr['date_str'] = helpers.format_date(nr['date'])
        response.append(nr)

    response.sort(key=lambda x: x['date'], reverse=True)
    utils.add_index(response)

    return response


@app.route('/api/1.0/stats/bp')
@decorators.jsonify('stats')
@decorators.exception_handler()
@decorators.record_filter()
def get_bpd(records, **kwargs):
    result = []
    for record in records:
        if record['record_type'] in ['bpd', 'bpc']:
            record = vault.extend_record(record)
            mention_date = record.get('mention_date')
            if mention_date:
                date = helpers.format_date(mention_date)
            else:
                date = 'never'
            result.append({
                'date': date,
                'status': record['lifecycle_status'],
                'metric': record.get('mention_count') or 0,
                'id': record['name'],
                'name': record['name'],
                'link': helpers.make_blueprint_link(record['module'],
                                                    record['name'])
            })

    result.sort(key=lambda x: x['metric'], reverse=True)
    utils.add_index(result)

    return result


@app.route('/api/1.0/users')
@decorators.jsonify('users')
@decorators.exception_handler()
@decorators.record_filter(ignore='user_id')
@decorators.query_filter(query_param='user_name')
def get_users_json(record_ids, query_filter, **kwargs):
    user_ids = vault.get_memory_storage().get_index_keys_by_record_ids(
        'user_id', record_ids)

    result = []
    for user_id in user_ids:
        user_name = vault.get_user_from_runtime_storage(user_id)['user_name']
        if query_filter(user_name):
            result.append({'id': user_id, 'text': user_name})

    result.sort(key=lambda x: x['text'])
    return result


@app.route('/api/1.0/users/<user_id>')
@decorators.jsonify('user')
def get_user(user_id):
    user = vault.get_user_from_runtime_storage(user_id)
    if not user:
        flask.abort(404)
    user = helpers.extend_user(user)
    return user


@app.route('/api/1.0/releases')
@decorators.jsonify('releases')
@decorators.exception_handler()
@decorators.query_filter(query_param='query')
def get_releases_json(query_filter):
    return [{'id': r['release_name'], 'text': r['release_name'].capitalize()}
            for r in vault.get_release_options()
            if query_filter(r['release_name'])]


@app.route('/api/1.0/releases/<release>')
@decorators.jsonify('release')
def get_release_json(release):
    if release != 'all':
        if release not in vault.get_vault()['releases']:
            release = parameters.get_default('release')

    return {'id': release, 'text': release.capitalize()}


@app.route('/api/1.0/metrics')
@decorators.jsonify('metrics')
@decorators.exception_handler()
@decorators.query_filter(query_param='query')
def get_metrics_json(query_filter):
    return sorted([{'id': m, 'text': t}
                   for m, t in six.iteritems(parameters.METRIC_LABELS)
                   if query_filter(t)],
                  key=operator.itemgetter('text'))


@app.route('/api/1.0/metrics/<metric>')
@decorators.jsonify('metric')
@decorators.exception_handler()
def get_metric_json(metric):
    if metric not in parameters.METRIC_LABELS:
        metric = parameters.get_default('metric')
    return {'id': metric, 'text': parameters.METRIC_LABELS[metric]}


@app.route('/api/1.0/project_types')
@decorators.jsonify('project_types')
@decorators.exception_handler()
@decorators.query_filter(query_param='query')
def get_project_types_json(query_filter):
    return [{'id': pt['id'], 'text': pt['title'], 'items': pt.get('items', [])}
            for pt in vault.get_project_types() if query_filter(pt['title'])]


@app.route('/api/1.0/project_types/<project_type>')
@decorators.jsonify('project_type')
@decorators.exception_handler()
def get_project_type_json(project_type):
    if not vault.is_project_type_valid(project_type):
        project_type = parameters.get_default('project_type')

    pt = vault.get_project_type(project_type)
    return {'id': pt['id'], 'text': pt['title']}


def _get_week(kwargs, param_name):
    date_param = parameters.get_single_parameter(kwargs, param_name)
    if date_param:
        ts = utils.date_to_timestamp_ext(date_param)
    else:
        ts = vault.get_vault()[param_name]
    return utils.timestamp_to_week(ts)


@app.route('/api/1.0/stats/timeline')
@decorators.jsonify('timeline')
@decorators.exception_handler()
@decorators.record_filter(ignore=['release', 'start_date'])
def timeline(records, **kwargs):
    # find start and end dates
    metric = parameters.get_parameter(kwargs, 'metric')
    start_date = int(parameters.get_single_parameter(kwargs, 'start_date')
                     or 0)
    release_name = parameters.get_single_parameter(kwargs, 'release') or 'all'
    releases = vault.get_vault()['releases']

    if 'all' in release_name:
        start_week = release_start_week = _get_week(kwargs, 'start_date')
        end_week = release_end_week = _get_week(kwargs, 'end_date')
    else:
        release = releases[release_name]
        start_week = release_start_week = utils.timestamp_to_week(
            release['start_date'])
        end_week = release_end_week = utils.timestamp_to_week(
            release['end_date'])

    now = utils.timestamp_to_week(int(time.time())) + 1

    # expand start-end to year if needed
    if release_end_week - release_start_week < 52:
        expansion = (52 - (release_end_week - release_start_week)) // 2
        if release_end_week + expansion < now:
            end_week += expansion
        else:
            end_week = now
        start_week = end_week - 52

    # empty stats for all weeks in range
    weeks = range(start_week, end_week)
    week_stat_loc = dict((c, 0) for c in weeks)
    week_stat_commits = dict((c, 0) for c in weeks)
    week_stat_commits_hl = dict((c, 0) for c in weeks)

    if ('commits' in metric) or ('loc' in metric):
        handler = lambda record: record['loc']
    else:
        handler = lambda record: 0

    # fill stats with the data
    if 'man-days' in metric:
        # special case for man-day effort metric
        release_stat = collections.defaultdict(set)
        all_stat = collections.defaultdict(set)
        for record in records:
            if ((record['record_type'] == 'commit') or
                    (record['week'] not in weeks)):
                continue

            day = record['date'] // (24 * 3600)
            user = vault.get_user_from_runtime_storage(record['user_id'])
            if record['release'] == release_name:
                release_stat[day] |= set([user['seq']])
            all_stat[day] |= set([user['seq']])
        for day, users in six.iteritems(release_stat):
            week = utils.timestamp_to_week(day * 24 * 3600)
            week_stat_commits_hl[week] += len(users)
        for day, users in six.iteritems(all_stat):
            week = utils.timestamp_to_week(day * 24 * 3600)
            week_stat_commits[week] += len(users)
    else:
        for record in records:
            week = record['week']
            if week in weeks:
                week_stat_loc[week] += handler(record)
                week_stat_commits[week] += 1
                if 'members' in metric:
                    if record['date'] >= start_date:
                        week_stat_commits_hl[week] += 1
                else:
                    if record['release'] == release_name:
                        week_stat_commits_hl[week] += 1

    if 'all' == release_name and 'members' not in metric:
        week_stat_commits_hl = week_stat_commits

    # form arrays in format acceptable to timeline plugin
    array_loc = []
    array_commits = []
    array_commits_hl = []

    for week in weeks:
        week_str = utils.week_to_date(week)
        array_loc.append([week_str, week_stat_loc[week]])
        array_commits.append([week_str, week_stat_commits[week]])
        array_commits_hl.append([week_str, week_stat_commits_hl[week]])

    return [array_commits, array_commits_hl, array_loc]


gravatar = gravatar_ext.Gravatar(app, size=64, rating='g', default='wavatar')


@app.template_filter('make_url')
def to_url_params(dict_params, base_url):
    return base_url + '?' + '&'.join(
        ['%s=%s' % (k, v) for k, v in six.iteritems(dict_params)])


@app.template_filter('remove_ctrl_chars')
def remove_ctrl_chars(text):
    return re.sub(r'[\W]', '_', text)


def main():
    app.run(cfg.CONF.listen_host, cfg.CONF.listen_port)

if __name__ == '__main__':
    main()
