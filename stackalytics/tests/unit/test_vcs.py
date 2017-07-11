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

import mock
import testtools

from stackalytics.processor import vcs


class TestVcsProcessor(testtools.TestCase):
    def setUp(self):
        super(TestVcsProcessor, self).setUp()

        self.repo = {
            'module': 'dummy',
            'uri': 'git://git.openstack.org/dummy.git',
            'releases': []
        }
        self.git = vcs.Git(self.repo, '/tmp')
        self.chdir_patcher = mock.patch('os.chdir')
        self.chdir_patcher.start()

    def tearDown(self):
        super(TestVcsProcessor, self).tearDown()
        self.chdir_patcher.stop()

    def test_git_log(self):
        with mock.patch('sh.git') as git_mock:
            git_mock.return_value = '''
commit_id:b5a416ac344160512f95751ae16e6612aefd4a57
date:1369119386
author_name:Akihiro MOTOKI
author_email:motoki@da.jp.nec.com
subject:Remove class-based import in the code repo
message:Fixes bug 1167901.

This commit also removes backslashes for line break.

Change-Id: Id26fdfd2af4862652d7270aec132d40662efeb96

diff_stat:

 21 files changed, 340 insertions(+), 408 deletions(-)
commit_id:5be031f81f76d68c6e4cbaad2247044aca179843
date:1370975889
author_name:Monty Taylor
author_email:mordred@inaugust.com
subject:Remove explicit distribute depend.
message:Causes issues with the recent re-merge with setuptools. Advice from
upstream is to stop doing explicit depends.

Change-Id: I70638f239794e78ba049c60d2001190910a89c90

diff_stat:

 1 file changed, 1 deletion(-)
commit_id:2dcb4fa4aa1925ffbd90d1cc7556a13a1bc45d1c
date:1369831203
author_name:Mark McClain
author_email:mark.mcclain@dreamhost.com
subject:add readme for 2.2.2
message:Fixes bug: 1234567
Also fixes bug 987654
Change-Id: Id32a4a72ec1d13992b306c4a38e73605758e26c7

diff_stat:

 1 file changed, 8 insertions(+)
commit_id:06d321b6b7681b162cd3231b5bdd92b17eb4f401
date:1369831203
author_name:John Doe
author_email:john.doe@dreamhost.com
subject:add readme for 2.2.2
message: implements blueprint fix-me.
Co-Authored-By: Anonymous <wrong@email>
Change-Id: Id32a4a72ec1d13992b306c4a38e73605758e26c7

diff_stat:

 0 files changed
commit_id:913c86a9d5b6a1b74db36266e996cb4d6073f75b
date:1369831203
author_name:Doug Hoffner
author_email:mark.mcclain@dreamhost.com
subject:add readme for 2.2.2
message:Change-Id: Id32a4a72ec1d13992b306c4a38e73605758e26c7
Co-Authored-By: some friend of mine

diff_stat:

 0 files changed, 0 insertions(+), 0 deletions(-)
commit_id:2f3103a96c4d234a4fcc0b0211a20308c0d342e7
date:1397687866
author_name:James E. Blair
author_email:jeblair@openstack.org
subject:Reduce IAD usage by 50%
message:At provider's request.

Change-Id: I976eaff357bf0ad4bce2a7fd5fe6fd81750276c5

diff_stat:
commit_id:12811c76f3a8208b36f81e61451ec17d227b4e58
date:1369831203
author_name:Jimi Hendrix
author_email:jimi.hendrix@openstack.com
subject:adds support off co-authors
message:Change-Id: Id811c762ec1d13992b306c4a38e7360575e61451
Co-Authored-By: Tupac Shakur <tupac.shakur@openstack.com>
Also-By: Bob Dylan <bob.dylan@openstack.com>
Also-By: Anonymous <wrong@email>
Also-By: Winnie the Pooh winnie222@openstack.org

diff_stat:

 0 files changed, 0 insertions(+), 0 deletions(-)
commit_id:d1af9cbe0187e1a65cf1eb46fb1650cf619a7b3a
date:1369831300
author_name:Vasya Pupkin
author_email:vpupkinx@openstack.com
subject:adds new support of co-authors
message:Change-Id: I577dfdf7f65a0c883ddbcfda62daf8c5f9c746c1
Co-Authored-By: Tupac Shakur <tupac.shakur@openstack.com>
Also: Bob Dylan <bob.dylan@openstack.com>
Co-Authored: Anonymous <correct@email.com>
Co-Author-By: Anonymous2 <correct@email2.com>
co-authored-by: brian.tully@hp.com
Co-Author: Winnie the Pooh winnie222@openstack.org

diff_stat:

 0 files changed, 0 insertions(+), 0 deletions(-)
            '''
            commits = list(self.git.log('dummy', 'dummy'))

        commits_expected = 8
        self.assertEqual(commits_expected, len(commits))

        self.assertEqual(21, commits[0]['files_changed'])
        self.assertEqual(340, commits[0]['lines_added'])
        self.assertEqual(408, commits[0]['lines_deleted'])
        self.assertEqual(['1167901'], commits[0]['bug_id'])

        self.assertEqual(1, commits[1]['files_changed'])
        self.assertEqual(0, commits[1]['lines_added'])
        self.assertEqual(1, commits[1]['lines_deleted'])

        self.assertEqual(1, commits[2]['files_changed'])
        self.assertEqual(8, commits[2]['lines_added'])
        self.assertEqual(0, commits[2]['lines_deleted'])
        self.assertEqual(set(['987654', '1234567']),
                         set(commits[2]['bug_id']))

        self.assertEqual(0, commits[3]['files_changed'])
        self.assertEqual(0, commits[3]['lines_added'])
        self.assertEqual(0, commits[3]['lines_deleted'])
        self.assertEqual(set(['dummy:fix-me']),
                         set(commits[3]['blueprint_id']))
        self.assertNotIn('coauthor', commits[3])

        self.assertEqual(0, commits[4]['files_changed'])
        self.assertEqual(0, commits[4]['lines_added'])
        self.assertEqual(0, commits[4]['lines_deleted'])
        self.assertNotIn('coauthor', commits[4])

        self.assertEqual('jeblair@openstack.org', commits[5]['author_email'])
        self.assertEqual(0, commits[5]['files_changed'])
        self.assertEqual(0, commits[5]['lines_added'])
        self.assertEqual(0, commits[5]['lines_deleted'])

        self.assertIn(
            {'author_name': 'Tupac Shakur',
             'author_email': 'tupac.shakur@openstack.com'},
            commits[6]['coauthor'])

        self.assertIn(
            {'author_name': 'Bob Dylan',
             'author_email': 'bob.dylan@openstack.com'},
            commits[6]['coauthor'])

        self.assertIn(
            {'author_name': 'Winnie the Pooh',
             'author_email': 'winnie222@openstack.org'},
            commits[6]['coauthor'])

        self.assertIn(
            {'author_name': 'Tupac Shakur',
             'author_email': 'tupac.shakur@openstack.com'},
            commits[7]['coauthor'])

        self.assertNotIn(
            {'author_name': 'Bob Dylan',
             'author_email': 'bob.dylan@openstack.com'},
            commits[7]['coauthor'])

        self.assertNotIn(
            {'author_name': 'Anonymous',
             'author_email': 'correct@email.com'},
            commits[7]['coauthor'])

        self.assertNotIn(
            {'author_name': 'Anonymous2',
             'author_email': 'correct@email2.com'},
            commits[7]['coauthor'])

        self.assertIn(
            {'author_name': 'Winnie the Pooh',
             'author_email': 'winnie222@openstack.org'},
            commits[7]['coauthor'])

        self.assertIn(
            {'author_name': '',
             'author_email': 'brian.tully@hp.com'},
            commits[7]['coauthor'])
