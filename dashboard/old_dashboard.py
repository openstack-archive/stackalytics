# Copyright (C) 2013 Mirantis Inc
#
# Author: Ilya Shakhat <ishakhat@mirantis.com>

import cgi

import datetime as DT
import functools
import itertools
import json
import re
import sqlite3
import time
import urllib

import flask
from flask.ext import gravatar as gravatar_ext
from werkzeug.contrib import cache as cache_package

DATABASE = 'stackalytics.sqlite'
LAST_UPDATE = None
DEBUG = False
CACHE_ENABLED = False
CACHE_EXPIRATION = 5 * 60
CACHE_TYPE = 'simple'

# create our little application :)
app = flask.Flask(__name__)
app.config.from_object(__name__)
app.config.from_envvar('DASHBOARD_CONF', silent=True)

if app.config['CACHE_TYPE'] == 'memcached':
    cache = cache_package.MemcachedCache(['127.0.0.1:11211'])
else:
    cache = cache_package.SimpleCache()


# DB COMMON FUNCS ************************************************************


def get_db():
    """Opens a new database connection if there is none yet for the
    current application context.
    """
    top = flask._app_ctx_stack.top
    if not hasattr(top, 'sqlite_db'):
        top.sqlite_db = sqlite3.dbapi2.connect(app.config['DATABASE'])
        top.sqlite_db.row_factory = sqlite3.dbapi2.Row
    return top.sqlite_db


@app.teardown_appcontext
def close_database(exception):
    """Closes the database again at the end of the request."""
    top = flask._app_ctx_stack.top
    if hasattr(top, 'sqlite_db'):
        top.sqlite_db.close()


def query_db(query, args=(), one=False):
    """Queries the database and returns a list of dictionaries."""
    app.logger.debug(query)
    cur = get_db().execute(query, args)
    rv = cur.fetchall()
    return (rv[0] if rv else None) if one else rv


# DECORATORS *****************************************************************

def cached(timeout=app.config['CACHE_EXPIRATION'], key='view/%s', params=None):
    def decorator(f):
        @functools.wraps(f)
        def decorated_function(*args, **kwargs):
            if app.config['CACHE_ENABLED']:
                cache_key = key % flask.request.path
                if params:
                    cache_key += '/' + '/'.join(
                        [param + '=' + (flask.request.args.get(param) or '')
                         for param in params]
                    )
                cache_key = cache_key.replace(' ', '+')
                app.logger.debug('Cache key %s' % cache_key)
                rv = cache.get(cache_key)
                app.logger.debug('Got value from the cache \n%s' % rv)
                if rv is not None:
                    return rv
                rv = f(*args, **kwargs)
                cache.set(cache_key, rv, timeout=timeout)
                app.logger.debug('Set the cache \n%s' % rv)
                return rv
            else:
                return f(*args, **kwargs)
        return decorated_function
    return decorator


def templated(template=None):
    def decorator(f):
        @functools.wraps(f)
        def decorated_function(*args, **kwargs):
            template_name = template
            if template_name is None:
                template_name = (flask.request.endpoint.replace('.', '/') +
                                 '.html')
            ctx = f(*args, **kwargs)
            if ctx is None:
                ctx = {}
            elif not isinstance(ctx, dict):
                return ctx

            # put parameters into template
            metric = flask.request.args.get('metric')
            if metric not in METRIC_LABELS:
                metric = None
            ctx['metric'] = metric or DEFAULT_METRIC

            period = flask.request.args.get('period')
            if period not in PERIOD_LABELS:
                period = None
            ctx['period'] = period or DEFAULT_PERIOD
            ctx['metric_label'] = METRIC_LABELS[ctx['metric']]
            ctx['period_label'] = PERIOD_LABELS[ctx['period']]

            project_type = flask.request.args.get('project_type')
            if project_type not in PROJECT_TYPES:
                project_type = None
            ctx['project_type'] = project_type or DEFAULT_PROJECT_TYPE

            ctx['last_update'] = app.config['LAST_UPDATE']

            return flask.render_template(template_name, **ctx)
        return decorated_function
    return decorator


def verified():
    def decorator(f):
        @functools.wraps(f)
        def decorated_function(*args, **kwargs):
            if 'project_type' in kwargs:
                if kwargs['project_type'] not in ['CORE', 'INCUBATION', 'ALL']:
                    flask.abort(404)
            if 'module' in kwargs:
                res = query_db('select 1 from repositories where name = ?',
                               [kwargs['module'] + '.git'])
                if not res:
                    flask.abort(404)
            if 'company' in kwargs:
                company = urllib.unquote_plus(kwargs['company']).lower()
                res = query_db('select companies.name from people '
                               'join companies '
                               'on people.company_id = companies.id '
                               'where lower(companies.name) = ?',
                               [company])
                if not res:
                    flask.abort(404)
                kwargs['company'] = res[0][0]
            if 'engineer' in kwargs:
                res = query_db('select 1 from people where launchpad_id = ?',
                               [kwargs['engineer']])
                if not res:
                    flask.abort(404)
            return f(*args, **kwargs)
        return decorated_function
    return decorator


# UTIL FUNCS *****************************************************************

def clear_text(s):
    a = cgi.escape('\n'.join([a.strip() for a in s.split('\n') if a.strip()]))
    first, nl, remain = a.partition('\n')
    return '<b>' + first + '</b>' + nl + nl + remain


def link_blueprint(s, module):
    return re.sub(r'(blueprint\s+)([\w-]+)',
                  r'\1<a href="https://blueprints.launchpad.net/' +
                  module + r'/+spec/\2">\2</a>',
                  s)


def link_bug(s):
    return re.sub(r'([B|b]ug\s+)#?([\d]{5,7})',
                  r'\1<a href="https://bugs.launchpad.net/bugs/\2">\2</a>',
                  s)


def link_change_id(s):
    return re.sub(r'(I[0-9a-f]{40})',
                  r'<a href="https://review.openstack.org/#q,\1,n,z">\1</a>',
                  s)


def filter_over_limit(data, limit):
    if 1 < limit < len(data):
        s = 0
        for rec in data[limit - 1:]:
            s += rec['rank']
        data[limit - 1] = data[0].copy()
        data[limit - 1]['name'] = 'others'
        data[limit - 1]['rank'] = s
        data = data[:limit]
    return data


def paste_links(data, base_uri, metric, period, project_type):
    for one in data:
        if one['name']:
            one['link'] = ('<a href="/' + base_uri +
                           urllib.quote_plus(one['name']) +
                           '?metric=' + metric +
                           '&period=' + period +
                           '&project_type=' + project_type +
                           '">' + (one['name']) + '</a>')
        else:
            one['link'] = '<i>Unmapped</i>'
    return data


def index_column(data):
    n = 1
    for one in data:
        if one['name'] is None or one['name'][0] == '*':
            one['index'] = ''
        else:
            one['index'] = n
            n += 1
    return data

DEFAULT_METRIC = 'loc'
DEFAULT_PERIOD = 'havana'
DEFAULT_PROJECT_TYPE = 'incubation'

PERIODS = {
    'all': (DT.date(2010, 05, 1), DT.date(2013, 10, 1)),
    'essex': (DT.date(2011, 10, 1), DT.date(2012, 04, 1)),
    'folsom': (DT.date(2012, 04, 1), DT.date(2012, 10, 1)),
    'grizzly': (DT.date(2012, 10, 1), DT.date(2013, 04, 1)),
    'havana': (DT.date(2013, 04, 1), DT.date(2013, 10, 1)),
}

INDEPENDENT = '*independent'

METRIC_LABELS = {
    'loc': 'Lines of code',
    'commits': 'Commits',
}

PERIOD_LABELS = {
    'all': 'All times',
    'six_months': 'Last 6 months',
    'essex': 'Essex',
    'folsom': 'Folsom',
    'grizzly': 'Grizzly',
    'havana': 'Havana',
}

PROJECT_TYPES = {
    'core': ['core'],
    'incubation': ['core', 'incubation'],
    'all': ['core', 'incubation', 'dev'],
}

ISSUE_TYPES = ['bug', 'blueprint']


def extract_time_period(period):
    begin = DT.date(2010, 2, 1)
    end = DT.datetime.now().date()

    if not period or period == 'six_months':
        begin = end - DT.timedelta(days=182)
    elif period == 'all':
        begin = PERIODS[period][0]
    elif period in PERIODS:
        begin, end = PERIODS[period]

    return begin, end


def parse_time_period(period):
    begin, end = extract_time_period(period)
    return DT.date.isoformat(begin), DT.date.isoformat(end)


def parse_date_from_string_to_timestamp(datestring):
    d = DT.datetime.strptime(datestring, "%Y-%m-%d %H:%M:%S")
    return time.mktime(d.timetuple())


def get_period_filter(period):
    return '''
    and scmlog.date > ? and scmlog.date <= ?
    '''


def get_metric_filter(metric):
    if metric == 'loc':
        metric_filter = 'sum(commits_lines.added) + sum(commits_lines.removed)'
    else:
        metric_filter = 'count(*)'
    return metric_filter


def get_project_type_filter(project_type):
    if not project_type:
        project_type = DEFAULT_PROJECT_TYPE
    types = PROJECT_TYPES[project_type]
    fts = ["repositories.project_type = '%s'" % t for t in types]
    return 'and (' + ' or '.join(fts) + ')'


def extract_params():
    module = flask.request.args.get('module')
    limit = int(flask.request.args.get('limit') or 0)
    period = flask.request.args.get('period') or DEFAULT_PERIOD
    metric = flask.request.args.get('metric') or DEFAULT_METRIC
    project_type = (flask.request.args.get('project_type')
                    or DEFAULT_PROJECT_TYPE)
    return module, limit, period, metric, project_type


def row2dict(a):
    r = {}
    for key in a.keys():
        r.update({key: a[key]})
    return r


# UI HANDLERS ****************************************************************
# these handle page rendering

@app.route('/')
@templated('companies.html')
def overview():
    return {}


@app.errorhandler(404)
def page_not_found(e):
    return flask.render_template('404.html'), 404


@app.route('/companies')
@app.route('/companies/')
@app.route('/modules')
@app.route('/modules/')
def redirects():
    return flask.redirect(flask.url_for('overview'))


@app.route('/companies/<company>')
@templated()
@cached(params=['period', 'project_type'])
@verified()
def company_details(company):
    details = contribution_details(flask.request.args.get('period'),
                                   flask.request.args.get('project_type'),
                                   company=company)
    details.update({
        'company': company,
    })
    return details


@app.route('/engineers/')
@templated()
def engineers():
    return {}


@app.route('/modules/<module>')
@templated()
@cached()
@verified()
def module_details(module):
    commits_res = query_db('''
select scmlog.date, scmlog.message, people.launchpad_id, people.name,
        people.email, companies.name as company from scmlog
    join people on scmlog.author_id = people.id
    join companies on people.company_id = companies.id
where
    people.launchpad_id not null
    and scmlog.id in (
        select actions.commit_id from actions
            join branches on branches.id = actions.branch_id
        where branches.name = 'master'
       )
       and scmlog.repository_id in (
        select repositories.id from repositories
        where repositories.name = ?
       )
order by scmlog.date desc
limit 50
    ''', [module + '.git'])

    commits = []
    for record in commits_res:
        message = record['message']

        m = re.search(r'bug\s+(\d{5,7})', message)
        if m:
            ref = ('Bug: <a href="https://bugs.launchpad.net/bugs/' +
                   m.group(1) + '">' + m.group(1) + '</a>')
        else:
            m = re.search(r'blueprint\s+([\w-]+)', message)
            if m:
                ref = ('Blueprint: '
                       '<a href="https://blueprints.launchpad.net/' +
                       module + '/+spec/' + m.group(1) + '">' +
                       m.group(1) + '</a>')
            else:
                ref = None

        m = re.search(r'(I[0-9a-f]{40})', message)
        if m:
            change_id = m.group(1)
        else:
            change_id = None

        company = record['company']
        if company == INDEPENDENT:
            company = None

        text = message.split('\n')[0].strip()

        commits.append(
            {'date': parse_date_from_string_to_timestamp(record['date']),
             'ref': ref, 'text': text,
             'change_id': change_id,
             'launchpad_id': record['launchpad_id'],
             'name': record['name'], 'email': record['email'],
             'company': company})

    return {'module': module, 'commits': commits}


def contribution_details(period, project_type, engineer=None, company=None):
    if engineer:
        people_filter = 'people.launchpad_id'
        people_param = engineer
    elif company:
        people_filter = 'companies.name'
        people_param = company
    else:
        return None

    time_period = parse_time_period(period)

    commits_res = query_db('''
select scmlog.message, scmlog.date, repositories.name as repo,
       details.change_id, details.issue_type, details.issue_id,
       details.commit_type, commits_lines.added, commits_lines.removed
    from scmlog
    join repositories on scmlog.repository_id = repositories.id
    join details on scmlog.id = details.commit_id
    join commits_lines on commits_lines.commit_id = scmlog.id
where
    scmlog.author_id in (
        select people.id from people
        join companies on people.company_id = companies.id
        where ''' + people_filter + ''' = ?
       )
    and scmlog.id in (
        select actions.commit_id from actions
            join branches on branches.id = actions.branch_id
        where branches.name = 'master'
       )
    ''' + get_period_filter(period) +
                           get_project_type_filter(project_type) + '''
order by scmlog.date desc
        ''', [people_param, time_period[0], time_period[1]])

    blueprints = set()
    bugs = set()
    commits = []
    code_only_commits = 0
    test_only_commits = 0
    code_and_test_commits = 0
    loc = 0

    for c in commits_res:
        module = c['repo'].rpartition('.')[0]
        issue_type = c['issue_type']
        issue_id = c['issue_id']
        commit_type = c['commit_type']
        loc += c['added'] + c['removed']

        is_code = commit_type & 0x1
        if commit_type == 1:
            code_only_commits += 1
        is_test = commit_type & 0x2
        if commit_type == 2:
            test_only_commits += 1
        if commit_type == 3:
            code_and_test_commits += 1

        if issue_type == 'blueprint':
            blueprints.add((issue_id, module))
        elif issue_type == 'bug':
            bugs.add((issue_id, is_code, is_test))

        commits.append({
            'message': link_change_id(link_bug(link_blueprint(
                clear_text(c['message']), module))),
            'date': parse_date_from_string_to_timestamp(c['date']),
            'module': module,
            'is_code': is_code,
            'is_test': is_test,
            'added_loc': c['added'],
            'removed_loc': c['removed'],
        })

    return {
        'commits': commits,
        'blueprints': sorted(blueprints),
        'bugs': sorted(bugs, key=lambda rec: rec[0]),
        'code_only_commits': code_only_commits,
        'test_only_commits': test_only_commits,
        'code_and_test_commits': code_and_test_commits,
        'code_commits': (code_only_commits + test_only_commits +
                         code_and_test_commits),
        'non_code_commits': (len(commits) - code_only_commits -
                             test_only_commits - code_and_test_commits),
        'loc': loc,
    }


@app.route('/engineers/<engineer>')
@templated()
@cached(params=['period', 'project_type'])
@verified()
def engineer_details(engineer):
    details_res = query_db('''
        select people.name, companies.name as company,
            launchpad_id, email from people
        join companies on people.company_id = companies.id
        where people.launchpad_id = ? and end_date is null
    ''', [engineer])

    if not details_res:
        flask.abort(404)

    details = row2dict(details_res[0])

    commits = contribution_details(flask.request.args.get('period'),
                                   flask.request.args.get('project_type'),
                                   engineer=engineer)
    commits.update({
        'engineer': engineer,
        'details': details,
    })

    return commits


@app.route('/commits/')
@app.route('/commits/<issue_type>')
@templated()
@cached(params=['module', 'period', 'project_type'])
@verified()
def commits(issue_type=None):
    if issue_type is not None and issue_type not in ISSUE_TYPES:
        flask.abort(404)

    module, limit, period, metric, project_type = extract_params()
    time_period = parse_time_period(period)

    res = query_db('''
select scmlog.date, scmlog.message, repositories.name as repo,
        details.issue_id, details.issue_type, details.change_id,
        people.launchpad_id, people.name as author, companies.name as company,
        people.email
    from scmlog
join people on people.id = scmlog.author_id
join companies on people.company_id = companies.id
join repositories on repositories.id = scmlog.repository_id
join details on details.commit_id = scmlog.id
where
    1 = 1
''' + get_period_filter(period) + get_project_type_filter(project_type) + '''
order by scmlog.date desc
limit 2000
    ''', [time_period[0], time_period[1]])

    issues = {}
    for rec in res:
        #todo make it right (e.g. paging)
        if len(issues) > 200:
            break

        if issue_type is not None and issue_type != rec['issue_type']:
            continue

        module = rec['repo'].rpartition('.')[0]
        timestamp = parse_date_from_string_to_timestamp(rec['date'])
        item = {
            'message': link_change_id(link_bug(link_blueprint(
                clear_text(rec['message']), module))),
            'date': timestamp,
            'change_id': rec['change_id'],
            'author': rec['author'],
            'company': rec['company'],
            'launchpad_id': rec['launchpad_id'],
            'email': rec['email'],
            'module': module,
        }

        if issue_type is None:
            key = DT.datetime.utcfromtimestamp(timestamp).strftime('%d %b %Y')
        else:
            key = rec['issue_id']

        if key in issues:
            issues[key].append(item)
        else:
            issues[key] = [item]

    return {'issue_type': issue_type,
            'issues': sorted(
                [{'issue_id': key, 'items': value} for key, value in
                 issues.iteritems()], key=lambda rec: rec['items'][0]['date'],
                reverse=True)}


@app.route('/unmapped')
@templated()
def unmapped():
    res = query_db('''
        select name, email from people
        where launchpad_id is null
    ''')

    if not res:
        flask.abort(404)

    res = [{'name': a['name'], 'email': a['email']} for a in res
           if (re.match(r'[\w\d._-]+@[\w\d_.-]+$', a['email']) and
               a['name'] and a['name'] != 'root')]

    return {'details': res}


# AJAX HANDLERS **************************************************************
# these handle data retrieval for tables and charts


@app.route('/data/companies')
@cached(params=['limit', 'module', 'period', 'metric', 'project_type'])
def get_companies():
    module, limit, period, metric, project_type = extract_params()

    params = []

    if module:
        module_filter = '''
       and scmlog.repository_id in (
        select repositories.id from repositories
        where repositories.name = ?
       )
        '''
        params.append(module + '.git')
    else:
        module_filter = ''

    metric_filter = get_metric_filter(metric)

    time_period = parse_time_period(period)
    params.append(time_period[0])
    params.append(time_period[1])

    raw = query_db('''
select companies.name as company, ''' + metric_filter + ''' as rank from scmlog
    join people on scmlog.author_id = people.id
    join companies on people.company_id = companies.id
    join commits_lines on commits_lines.commit_id = scmlog.id
    join repositories on scmlog.repository_id = repositories.id
where
    companies.name != '*robots'
    and scmlog.id in (
        select actions.commit_id from actions
            join branches on branches.id = actions.branch_id
        where branches.name = 'master'
       )''' + module_filter + get_period_filter(period) +
                   get_project_type_filter(project_type) + '''
group by people.company_id
order by rank desc
    ''', params)

    data = [{'name': rec['company'], 'rank': rec['rank']}
            for rec in raw
            if rec['company'] is not None]
    data = index_column(
        paste_links(filter_over_limit(data, limit), 'companies/', metric,
                    period, project_type))
    return json.dumps({'aaData': data})


@app.route('/data/companies/<company>')
@cached(params=['limit', 'period', 'metric', 'project_type'])
@verified()
def get_company_details(company):
    module, limit, period, metric, project_type = extract_params()
    time_period = parse_time_period(period)

    raw = query_db('''
select ''' + get_metric_filter(metric) + ''' as rank, people.name,
    people.launchpad_id from people
left join (
select * from scmlog
    join actions on actions.commit_id = scmlog.id
    join branches on branches.id = actions.branch_id
    join repositories on scmlog.repository_id = repositories.id
    where branches.name = 'master'
''' + get_period_filter(period) + get_project_type_filter(project_type) + '''
group by scmlog.id
) as scm on people.id = scm.author_id
join commits_lines on commits_lines.commit_id = scm.id
join companies on people.company_id = companies.id
where companies.name = ?
group by people.name
order by rank desc
        ''', [time_period[0], time_period[1], company])

    data = [{'rank': rec[0], 'name': rec[1], 'launchpad_id': rec[2]}
            for rec in raw]
    data = index_column(filter_over_limit(data, limit))
    for one in data:
        if one['launchpad_id']:
            one['link'] = ('<a href="/engineers/' + (one['launchpad_id']) +
                           '?metric=' + metric + '&period=' + period +
                           '&project_type=' + project_type + '">' +
                           (one['name']) + '</a>')
        else:
            one['link'] = one['name']
    return json.dumps({'aaData': data})


@app.route('/data/modules')
@cached(params=['limit', 'company', 'engineer', 'period', 'metric',
                'project_type'])
def get_modules():
    module, limit, period, metric, project_type = extract_params()
    company = flask.request.args.get('company')
    engineer = flask.request.args.get('engineer')

    params = []

    if engineer:
        eng_filter = "and people.launchpad_id = ?"
        params.append(engineer)
    else:
        eng_filter = ''
    if company:
        company_filter = "and companies.name = ?"
        params.append(company)
    else:
        # if no company filter out all robots
        company_filter = "and companies.name != '*robots'"

    time_period = parse_time_period(period)
    params.append(time_period[0])
    params.append(time_period[1])

    raw = query_db('''
select repositories.name as repo, ''' + get_metric_filter(metric) + ''' as rank
from scmlog
    join people on scmlog.author_id = people.id
    join repositories on scmlog.repository_id = repositories.id
    join commits_lines on commits_lines.commit_id = scmlog.id
    join companies on people.company_id = companies.id
where
    scmlog.id in (
        select actions.commit_id from actions
            join branches on branches.id = actions.branch_id
        where branches.name = 'master'
       )
''' + eng_filter + company_filter + get_period_filter(period) +
                   get_project_type_filter(project_type) + '''
group by scmlog.repository_id
order by rank desc
    ''', params)

    data = [{'name': rec[0].rpartition('.')[0], 'rank': rec[1]} for rec in raw]
    data = index_column(
        paste_links(filter_over_limit(data, limit), 'modules/', metric, period,
                    project_type))
    return json.dumps({'aaData': data})


@app.route('/data/engineers')
@cached(params=['limit', 'module', 'period', 'metric', 'project_type'])
def get_engineers():
    module, limit, period, metric, project_type = extract_params()

    params = []

    if module:
        module_filter = '''
       and scmlog.repository_id in (
        select repositories.id from repositories
        where repositories.name = ?
       )
        '''
        params.append(module + '.git')
    else:
        module_filter = ''

    metric_filter = get_metric_filter(metric)

    time_period = parse_time_period(period)
    params.append(time_period[0])
    params.append(time_period[1])

    raw = query_db('''
select people.name, people.launchpad_id, ''' + metric_filter + ''' as rank
from scmlog
    join people on scmlog.author_id = people.id
    join commits_lines on commits_lines.commit_id = scmlog.id
    join repositories on scmlog.repository_id = repositories.id
where
    people.email != 'review@openstack.org'
    and people.email != 'jenkins@review.openstack.org'
    and people.email != 'jenkins@openstack.org'
    and scmlog.id in (
        select actions.commit_id from actions
            join branches on branches.id = actions.branch_id
        where branches.name = 'master'
       )''' + module_filter + get_period_filter(period) +
                   get_project_type_filter(project_type) +
                   '''
                   group by people.name
                   order by rank desc
                       ''', params)

    data = [{'name': rec['name'], 'rank': rec['rank'],
             'launchpad_id': rec['launchpad_id']} for rec in raw]
    data = index_column(filter_over_limit(data, limit))
    for one in data:
        if one['launchpad_id']:
            one['link'] = ('<a href="/engineers/' + (one['launchpad_id']) +
                           '?metric=' + metric + '&period=' + period +
                           '&project_type' + project_type + '">' +
                           (one['name']) + '</a>')
        else:
            one['link'] = one['name']
    return json.dumps({'aaData': data})


@app.route('/data/timeline')
@cached(params=['company', 'engineer', 'period', 'metric', 'project_type'])
def get_timeline():

    company = flask.request.args.get('company')
    engineer = flask.request.args.get('engineer')
    module, limit, period, metric, project_type = extract_params()

    params = []
    if company:
        company_filter = 'and companies.name = ?'
        params.append(company)
    else:
        company_filter = "and companies.name != '*robots'"

    if engineer:
        engineer_filter = '''
       and scmlog.author_id in (
        select people.id from people
        where people.launchpad_id = ?
       )
        '''
        params.append(engineer)
    else:
        engineer_filter = ''

    if module:
        module_filter = '''
       and scmlog.repository_id in (
        select repositories.id from repositories
        where repositories.name = ?
       )
        '''
        params.append(module + '.git')
    else:
        module_filter = ''

    records = query_db('''
select scmlog.date, commits_lines.added + commits_lines.removed as rank
from scmlog
join commits_lines on commits_lines.commit_id = scmlog.id
join people on people.id = scmlog.author_id
join repositories on scmlog.repository_id = repositories.id
join companies on people.company_id = companies.id
where
    scmlog.id in (
        select actions.commit_id from actions
            join branches on branches.id = actions.branch_id
        where branches.name = 'master'
       )
''' + company_filter + engineer_filter + module_filter +
                       get_project_type_filter(project_type) + '''
order by scmlog.date
    ''', params)

    start_date = DT.date(2010, 5, 1)

    def mkdate2(datestring):
        return DT.datetime.strptime(datestring, "%Y-%m-%d %H:%M:%S").date()

    def week(date):
        return (date - start_date).days // 7

    def week_rev(n):
        return start_date + DT.timedelta(days=n * 7)

    dct_rank = {}
    dct_count = {}
    t = map(lambda (rec): [mkdate2(str(rec[0])), rec[1]], records)

    for key, grp in itertools.groupby(t, key=lambda (pair): week(pair[0])):
        grp_as_list = list(grp)
        dct_rank[key] = sum([x[1] for x in grp_as_list])
        dct_count[key] = len(grp_as_list)

    last = week(DT.datetime.now().date())
    res_rank = []
    res_count = []

    for n in range(1, last + 1):
        if n not in dct_rank:
            dct_rank[n] = 0
            dct_count[n] = 0

        rev = week_rev(n)
        res_rank.append([str(rev) + ' 0:00AM', dct_rank[n]])
        res_count.append([str(rev) + ' 0:00AM', dct_count[n]])

    begin, end = extract_time_period(period)
    begin = week(begin)
    end = week(end)
    u_begin = len(res_count) - 52
    u_end = len(res_count)

    if period == 'all':
        begin = 0
        u_begin = 0
        end = u_end
    elif period != 'six_months':
        if u_end > end + 13:
            u_end = end + 13
            u_begin = u_end - 52

    return json.dumps([res_count[u_begin:u_end],
                       res_count[begin:end],
                       res_rank[u_begin:u_end]])


# JINJA FILTERS **************************************************************
# some useful filters to help with data formatting

@app.template_filter('datetimeformat')
def format_datetime(timestamp):
    return DT.datetime.utcfromtimestamp(timestamp).strftime('%d %b %Y @ %H:%M')


@app.template_filter('launchpadmodule')
def format_launchpad_module_link(module):
    return '<a href="https://launchpad.net/%s">%s</a>' % (module, module)


@app.template_filter('encode')
def safe_encode(s):
    return urllib.quote_plus(s)


gravatar = gravatar_ext.Gravatar(app,
                                 size=100,
                                 rating='g',
                                 default='wavatar',
                                 force_default=False,
                                 force_lower=False)

# APPLICATION LAUNCHER *******************************************************

if __name__ == '__main__':
    app.run('0.0.0.0')
