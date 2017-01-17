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

import memcache


def check(expected, actual):
    if expected != actual:
        print('Expected: %s\nActual: %s' % (expected, actual))


def main():
    m = memcache.Client(['localhost:11211'])
    count = m.get('user:count') + 1
    users = [m.get('user:%d' % seq) for seq in range(count)]
    users = [u for u in users if u]

    for u in users:
        user_id = u.get('user_id')
        lp = u.get('launchpad_id')
        g = u.get('gerrit_id')
        emails = u.get('emails')

        if user_id:
            check(u, m.get('user:%s' % user_id.encode('utf8')))

        if lp:
            check(u, m.get('user:%s' % lp.encode('utf8')))

        if g:
            check(u, m.get('user:gerrit:%s' % g.encode('utf8')))

        if emails:
            for e in emails:
                check(u, m.get('user:%s' % e.encode('utf8')))


if __name__ == '__main__':
    main()
