import mock
import os
import testtools

from oslo.config import cfg

from stackalytics.processor import vcs


class TestVcsProcessor(testtools.TestCase):
    def setUp(self):
        super(TestVcsProcessor, self).setUp()

        self.repo = {
            'uri': 'git://github.com/dummy.git',
            'releases': []
        }
        self.git = vcs.Git(self.repo, '/tmp')
        cfg.CONF.sources_root = ''
        os.chdir = mock.Mock()

    def test_git_log(self):
        with mock.patch('sh.git') as git_mock:
            git_mock.return_value = '''
commit_id:b5a416ac344160512f95751ae16e6612aefd4a57
date:1369119386
author:Akihiro MOTOKI
author_email:motoki@da.jp.nec.com
author_email:motoki@da.jp.nec.com
subject:Remove class-based import in the code repo
message:Fixes bug 1167901

This commit also removes backslashes for line break.

Change-Id: Id26fdfd2af4862652d7270aec132d40662efeb96

diff_stat:

 21 files changed, 340 insertions(+), 408 deletions(-)
commit_id:5be031f81f76d68c6e4cbaad2247044aca179843
date:1370975889
author:Monty Taylor
author_email:mordred@inaugust.com
author_email:mordred@inaugust.com
subject:Remove explicit distribute depend.
message:Causes issues with the recent re-merge with setuptools. Advice from
upstream is to stop doing explicit depends.

Change-Id: I70638f239794e78ba049c60d2001190910a89c90

diff_stat:

 1 file changed, 1 deletion(-)
commit_id:92811c76f3a8308b36f81e61451ec17d227b453b
date:1369831203
author:Mark McClain
author_email:mark.mcclain@dreamhost.com
author_email:mark.mcclain@dreamhost.com
subject:add readme for 2.2.2
message:Change-Id: Id32a4a72ec1d13992b306c4a38e73605758e26c7

diff_stat:

 1 file changed, 8 insertions(+)
commit_id:92811c76f3a8308b36f81e61451ec17d227b453b
date:1369831203
author:John Doe
author_email:john.doe@dreamhost.com
author_email:john.doe@dreamhost.com
subject:add readme for 2.2.2
message:Change-Id: Id32a4a72ec1d13992b306c4a38e73605758e26c7

diff_stat:

 0 files changed
commit_id:92811c76f3a8308b36f81e61451ec17d227b453b
date:1369831203
author:Doug Hoffner
author_email:mark.mcclain@dreamhost.com
author_email:mark.mcclain@dreamhost.com
subject:add readme for 2.2.2
message:Change-Id: Id32a4a72ec1d13992b306c4a38e73605758e26c7

diff_stat:

 0 files changed, 0 insertions(+), 0 deletions(-)
            '''

        commits = list(self.git.log('dummy', 'dummy'))
        self.assertEquals(5, len(commits))

        self.assertEquals(21, commits[0]['files_changed'])
        self.assertEquals(340, commits[0]['lines_added'])
        self.assertEquals(408, commits[0]['lines_deleted'])

        self.assertEquals(1, commits[1]['files_changed'])
        self.assertEquals(0, commits[1]['lines_added'])
        self.assertEquals(1, commits[1]['lines_deleted'])

        self.assertEquals(1, commits[2]['files_changed'])
        self.assertEquals(8, commits[2]['lines_added'])
        self.assertEquals(0, commits[2]['lines_deleted'])

        self.assertEquals(0, commits[3]['files_changed'])
        self.assertEquals(0, commits[3]['lines_added'])
        self.assertEquals(0, commits[3]['lines_deleted'])

        self.assertEquals(0, commits[4]['files_changed'])
        self.assertEquals(0, commits[4]['lines_added'])
        self.assertEquals(0, commits[4]['lines_deleted'])
