import cgi
import datetime
import functools
import json
import os
import re
import urllib

import flask
from flask.ext import gravatar as gravatar_ext
import time

from dashboard import memory_storage
from stackalytics.processor.persistent_storage import PersistentStorageFactory
from stackalytics.processor.runtime_storage import RuntimeStorageFactory
from stackalytics.processor import user_utils

DEBUG = True
RUNTIME_STORAGE_URI = 'memcached://127.0.0.1:11211'
PERSISTENT_STORAGE_URI = 'mongodb://localhost'

# create our little application :)
app = flask.Flask(__name__)
app.config.from_object(__name__)
app.config.from_envvar('DASHBOARD_CONF', silent=True)


def get_vault():
    vault = getattr(app, 'stackalytics_vault', None)
    if not vault:
        vault = {}
        vault['runtime_storage'] = RuntimeStorageFactory.get_storage(
            RUNTIME_STORAGE_URI)
        vault['persistent_storage'] = PersistentStorageFactory.get_storage(
            PERSISTENT_STORAGE_URI)
        vault['memory_storage'] = (
            memory_storage.MemoryStorageFactory.get_storage(
                memory_storage.MEMORY_STORAGE_CACHED,
                vault['runtime_storage'].get_update(os.getpid())))

        releases = vault['persistent_storage'].get_releases()
        vault['releases'] = dict((r['release_name'].lower(), r)
                                 for r in releases)
        app.stackalytics_vault = vault
    return vault


def get_memory_storage():
    return get_vault()['memory_storage']


def record_filter(parameter_getter=lambda x: flask.request.args.get(x)):
    def decorator(f):
        @functools.wraps(f)
        def decorated_function(*args, **kwargs):

            vault = get_vault()
            memory_storage = vault['memory_storage']
            record_ids = memory_storage.get_record_ids()

            param = parameter_getter('modules')
            if param:
                record_ids &= memory_storage.get_record_ids_by_modules(
                    param.split(','))

            if 'launchpad_id' in kwargs:
                param = kwargs['launchpad_id']
            else:
                param = (parameter_getter('launchpad_id') or
                         parameter_getter('launchpad_ids'))
            if param:
                record_ids &= memory_storage.get_record_ids_by_launchpad_ids(
                    param.split(','))

            if 'company' in kwargs:
                param = kwargs['company']
            else:
                param = (parameter_getter('company') or
                         parameter_getter('companies'))
            if param:
                record_ids &= memory_storage.get_record_ids_by_companies(
                    param.split(','))

            param = parameter_getter('release') or parameter_getter('releases')
            if param:
                if param != 'all':
                    record_ids &= memory_storage.get_record_ids_by_releases(
                        c.lower() for c in param.split(','))

            kwargs['records'] = memory_storage.get_records(record_ids)
            return f(*args, **kwargs)

        return decorated_function

    return decorator


def aggregate_filter():
    def decorator(f):
        @functools.wraps(f)
        def decorated_function(*args, **kwargs):

            metric_filter = lambda r: r['loc']
            metric_param = flask.request.args.get('metric')
            if metric_param:
                metric = metric_param.lower()
                if metric == 'commits':
                    metric_filter = lambda r: 1
                elif metric != 'loc':
                    raise Exception('Invalid metric %s' % metric)

            kwargs['metric_filter'] = metric_filter
            return f(*args, **kwargs)

        return decorated_function

    return decorator


def exception_handler():
    def decorator(f):
        @functools.wraps(f)
        def decorated_function(*args, **kwargs):
            try:
                return f(*args, **kwargs)
            except Exception as e:
                print e
                flask.abort(404)

        return decorated_function

    return decorator


DEFAULT_METRIC = 'loc'
DEFAULT_RELEASE = 'havana'
DEFAULT_PROJECT_TYPE = 'incubation'

INDEPENDENT = '*independent'

METRIC_LABELS = {
    'loc': 'Lines of code',
    'commits': 'Commits',
}

PROJECT_TYPES = {
    'core': ['core'],
    'incubation': ['core', 'incubation'],
    'all': ['core', 'incubation', 'dev'],
}

ISSUE_TYPES = ['bug', 'blueprint']

DEFAULT_RECORDS_LIMIT = 10


def templated(template=None):
    def decorator(f):
        @functools.wraps(f)
        def decorated_function(*args, **kwargs):

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
            ctx['metric'] = metric or DEFAULT_METRIC
            ctx['metric_label'] = METRIC_LABELS[ctx['metric']]

            release = flask.request.args.get('release')
            releases = vault['releases']
            if release:
                release = release.lower()
                if release not in releases:
                    release = None
                else:
                    release = releases[release]['release_name']
            ctx['release'] = (release or DEFAULT_RELEASE).lower()

            return flask.render_template(template_name, **ctx)

        return decorated_function

    return decorator


@app.route('/')
@templated()
def overview():
    pass


def contribution_details(records, limit=DEFAULT_RECORDS_LIMIT):
    blueprints_map = {}
    bugs_map = {}
    commits = []
    loc = 0

    for record in records:
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
        'loc': loc,
    }
    return result


@app.route('/companies/<company>')
@exception_handler()
@templated()
@record_filter()
def company_details(company, records):
    details = contribution_details(records)
    details['company'] = company
    return details


@app.route('/modules/<module>')
@exception_handler()
@templated()
@record_filter()
def module_details(module, records):
    details = contribution_details(records)
    details['module'] = module
    return details


@app.route('/engineers/<launchpad_id>')
@exception_handler()
@templated()
@record_filter()
def engineer_details(launchpad_id, records):
    persistent_storage = get_vault()['persistent_storage']
    user = list(persistent_storage.get_users(launchpad_id=launchpad_id))[0]

    details = contribution_details(records)
    details['launchpad_id'] = launchpad_id
    details['user'] = user
    return details


@app.errorhandler(404)
def page_not_found(e):
    return flask.render_template('404.html'), 404


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
                                     get_memory_storage().get_launchpad_ids(),
                                     'launchpad_id', 'author')
    return json.dumps(response)


@app.route('/data/timeline')
@exception_handler()
@record_filter(parameter_getter=lambda x: flask.request.args.get(x)
               if (x != "release") and (x != "releases") else None)
def timeline(records):

    # find start and end dates
    release_name = flask.request.args.get('release')

    if not release_name:
        release_name = DEFAULT_RELEASE
    else:
        release_name = release_name.lower()

    releases = get_vault()['releases']
    if release_name not in releases:
        flask.abort(404)
    release = releases[release_name]

    start_date = release_start_date = user_utils.timestamp_to_week(
        user_utils.date_to_timestamp(release['start_date']))
    end_date = release_end_date = user_utils.timestamp_to_week(
        user_utils.date_to_timestamp(release['end_date']))
    now = user_utils.timestamp_to_week(int(time.time()))

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

    # fill stats with the data
    for record in records:
        week = record['week']
        if week in weeks:
            week_stat_loc[week] += record['loc']
            week_stat_commits[week] += 1

    # form arrays in format acceptable to timeline plugin
    array_loc = []
    array_commits = []
    array_commits_hl = []

    for week in weeks:
        week_str = user_utils.week_to_date(week)
        array_loc.append([week_str, week_stat_loc[week]])
        if release_start_date <= week <= release_end_date:
            array_commits_hl.append([week_str, week_stat_commits[week]])
        array_commits.append([week_str, week_stat_commits[week]])

    return json.dumps([array_commits, array_commits_hl, array_loc])


# Jinja Filters

@app.template_filter('datetimeformat')
def format_datetime(timestamp):
    return datetime.datetime.utcfromtimestamp(
        timestamp).strftime('%d %b %Y @ %H:%M')


@app.template_filter('launchpadmodule')
def format_launchpad_module_link(module):
    return '<a href="https://launchpad.net/%s">%s</a>' % (module, module)


@app.template_filter('encode')
def safe_encode(s):
    return urllib.quote_plus(s)


@app.template_filter('link')
def make_link(title, uri=None):
    return '<a href="%(uri)s">%(title)s</a>' % {'uri': uri, 'title': title}


def clear_text(s):
    return cgi.escape(re.sub(r'\n{2,}', '\n', s, flags=re.MULTILINE))


def link_blueprint(s, module):
    return re.sub(r'(blueprint\s+)([\w-]+)',
                  r'\1<a href="https://blueprints.launchpad.net/' +
                  module + r'/+spec/\2">\2</a>',
                  s, flags=re.IGNORECASE)


def link_bug(s):
    return re.sub(r'(bug\s+)#?([\d]{5,7})',
                  r'\1<a href="https://bugs.launchpad.net/bugs/\2">\2</a>',
                  s, flags=re.IGNORECASE)


def link_change_id(s):
    return re.sub(r'\s+(I[0-9a-f]{40})',
                  r' <a href="https://review.openstack.org/#q,\1,n,z">\1</a>',
                  s)


@app.template_filter('commit_message')
def make_commit_message(record):

    return link_change_id(link_bug(link_blueprint(clear_text(
        record['message']), record['module'])))


gravatar = gravatar_ext.Gravatar(app,
                                 size=100,
                                 rating='g',
                                 default='wavatar',
                                 force_default=False,
                                 force_lower=False)

if __name__ == '__main__':
    app.run('0.0.0.0')
