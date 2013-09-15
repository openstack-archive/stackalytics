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

import gzip
import httplib
import StringIO

from email import utils as email_utils
import re
import time
import urlparse

from stackalytics.openstack.common import log as logging
from stackalytics.processor import utils


LOG = logging.getLogger(__name__)

EMAIL_HEADER_PATTERN = ('From \S+(?: at \S+)?\s+'
                        '\w{3}\s+\w{3}\s+\d{1,2}\s+\d{2}:\d{2}(?::\d{2})?'
                        '(?:\s+\S+)?\s+\d{4}.*?\n')

MAIL_BOX_PATTERN = re.compile(
    '^' + EMAIL_HEADER_PATTERN +
    'From: (\S+(?: at \S+))(?:\W+(\w+(?:\s\w+)*))?.*?\n'
    'Date: (.*?)\n'
    'Subject: (.*?)(?=\n\S+:)'
    '.*?Message-ID: (\S+)\n'
    '\n(.*?)\n'
    '(?=' + EMAIL_HEADER_PATTERN + 'From: )',
    flags=re.MULTILINE | re.DOTALL)

MESSAGE_PATTERNS = {
    'bug_id': re.compile(r'https://bugs.launchpad.net/bugs/(?P<id>\d+)',
                         re.IGNORECASE),
    'blueprint_id': re.compile(r'https://blueprints.launchpad.net/'
                               r'(?P<module>[^\/]+)/\+spec/(?P<id>[a-z0-9-]+)',
                               re.IGNORECASE),
}

TRAILING_RECORD = ('From ishakhat at mirantis.com  Tue Sep 17 07:30:43 2013'
                   'From: ')


def _get_mail_archive_links(uri):
    content = utils.read_uri(uri)
    links = set(re.findall(r'\shref\s*=\s*[\'"]([^\'"]*\.txt\.gz)', content,
                           flags=re.IGNORECASE))
    return [urlparse.urljoin(uri, link) for link in links]


def _link_content_changed(link, runtime_storage_inst):
    LOG.debug('Check changes for mail archive located at uri: %s', link)
    parsed_uri = urlparse.urlparse(link)
    conn = httplib.HTTPConnection(parsed_uri.netloc)
    conn.request('HEAD', parsed_uri.path)
    res = conn.getresponse()
    last_modified = res.getheader('last-modified')

    if last_modified != runtime_storage_inst.get_by_key('mail_link:' + link):
        LOG.debug('Mail archive changed, last modified at: %s', last_modified)
        runtime_storage_inst.set_by_key('mail_link:' + link, last_modified)
        return True

    return False


def _retrieve_mails(uri):
    LOG.debug('Retrieving mail archive from uri: %s', uri)
    content = utils.read_uri(uri)
    gzip_fd = gzip.GzipFile(fileobj=StringIO.StringIO(content))
    content = gzip_fd.read()
    LOG.debug('Mail archive is loaded, start processing')

    content += TRAILING_RECORD

    for rec in re.finditer(MAIL_BOX_PATTERN, content):

        author_email = rec.group(1).replace(' at ', '@', 1)
        if not utils.check_email_validity(author_email):
            continue

        author_name = rec.group(2)
        date = int(time.mktime(email_utils.parsedate(rec.group(3))))
        subject = rec.group(4)
        message_id = rec.group(5)
        body = rec.group(6)

        email = {
            'message_id': message_id,
            'author_name': author_name,
            'author_email': author_email,
            'subject': subject,
            'date': date,
        }

        for pattern_name, pattern in MESSAGE_PATTERNS.iteritems():
            collection = set()
            for item in re.finditer(pattern, body):
                groups = item.groupdict()
                collection.add(groups['id'])
                if 'module' in groups:
                    email['module'] = groups['module']
            email[pattern_name] = list(collection)

        yield email


def log(uri, runtime_storage_inst):

    links = _get_mail_archive_links(uri)
    for link in links:
        if _link_content_changed(link, runtime_storage_inst):
            for mail in _retrieve_mails(link):
                LOG.debug('New mail: %s', mail)
                yield mail
