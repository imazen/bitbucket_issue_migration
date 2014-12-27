# -*- coding: utf-8 -*-

import json
import sys
import subprocess

TEMPLATE = """\
--pretty=format:'{"commit":"%H","author":"%an <%ae>","date":"%ad","message":"%B"},'
"""

class GitFrontend(object):

    def __init__(self, git_path):
        self.git_path = git_path

    def get_rev_msg(self, rev, format):
        cmd = [
            'git', 'show', '--no-patch', '--date=iso', '--pretty=format:%s' % format, rev
        ]
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, cwd=self.git_path)
        out, err = p.communicate()
        out = safe_decode(out)
        return out

    def get_rev_msg_obj(self, rev):
        r = {}
        r['revnum'] = rev
        r['node'] = self.get_rev_msg(rev, '%H')
        r['date'] = self.get_rev_msg(rev, '%ad')
        r['email'] = self.get_rev_msg(rev, '%ae')
        r['desc'] = self.get_rev_msg(rev, '%B')
        return r

    def get_changelog(self):
        cmd = ['git', 'log', '--date-order', '--reverse', '--pretty=format:%H']
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, cwd=self.git_path)
        out, err = p.communicate()
        out = safe_decode(out)
        return [l.strip() for l in out.splitlines() if l.strip()]


def safe_decode(s):
    if isinstance(s, unicode):
        return s

    for e in ('utf-8', 'mbcs'):
        try:
            return unicode(s, e)
        except UnicodeDecodeError:
            pass
    return unicode(s, 'utf-8', 'replace')


def to_console(git_path):
    f = GitFrontend(git_path)
    messages = (f.get_rev_msg(rev, TEMPLATE) for rev in f.get_changelog())
    for m in messages:
        print m



def to_json(git_path, outfile):
    f = GitFrontend(git_path)
    message_count = len(f.get_changelog())
    messages = (f.get_rev_msg_obj(r) for r in f.get_changelog())
    class StreamArray(list):
        def __len__(self):
            return message_count
        def __iter__(self):
            return messages
    json.dump({'messages': StreamArray()}, open(outfile, 'w'), indent=4)


if __name__ == '__main__':
    try:
        repo_path, outfile = sys.argv[1:3]
    except (ValueError, IndexError):
        print('Usage:\n  {} repository_path output.json'.format(sys.argv[0]))
        sys.exit(-1)

    to_json(repo_path, outfile)
    # to_console(repo_path)
