# -*- coding: utf-8 -*-

from mercurial.cmdutil import show_changeset
from mercurial.ui import ui as _ui
from mercurial.hg import repository
from mercurial import context
import os
import json
import sys

TEMPLATE = '{node|short} | {date|isodatesec} | {author|user}: {desc|strip|firstline}'


class Frontend(object):
    def __init__(self, path):
        self.ui = _ui()
        self.ui.readconfig(os.path.join(path, ".hg", "hgrc"))
        self.repo = repository(self.ui, path)

    def get_rev_msg(self, revision_hash, template=TEMPLATE):
        self.displayer = show_changeset(self.ui, self.repo, {'template': template}, False)
        self.ui.pushbuffer()
        rev = self.repo.lookup(revision_hash)
        ctx = context.changectx(self.repo, rev)
        self.displayer.show(ctx)
        msg = self.ui.popbuffer()
        return msg

    def get_changelog(self):
        return self.repo.changelog


def get_rev_messages(hg_path, template):
    f = Frontend(hg_path)
    messages = (f.get_rev_msg(rev, template) for rev in f.get_changelog())
    return messages


def safe_decode(s):
    if isinstance(s, unicode):
        return s

    for e in ('utf-8', 'mbcs'):
        try:
            return unicode(s, e)
        except UnicodeDecodeError:
            pass
    return unicode(s, 'utf-8', 'replace')


def to_console(hg_path):
    messages = get_rev_messages(hg_path, TEMPLATE)
    for m in messages:
        print m


def to_json(hg_path, outfile):
    f = Frontend(hg_path)
    messages = []
    for rev in f.get_changelog():
        r = {}
        r['revnum'] = rev
        r['node'] = f.get_rev_msg(rev, '{node}')
        r['date'] = f.get_rev_msg(rev, '{date|isodatesec}')
        r['email'] = f.get_rev_msg(rev, '{author}')
        desc = f.get_rev_msg(rev, '{desc}')
        r['desc'] = safe_decode(desc)
        messages.append(r)

    json.dump({'messages': messages}, open(outfile, 'w'), indent=4)


if __name__ == '__main__':
    os.environ['HGENCODING'] = 'utf8'
    try:
        repo_path, outfile = sys.argv[1:3]
    except (ValueError, IndexError):
        print('Usage:\n  {} repository_path output.json'.format(sys.argv[0]))
        sys.exit(-1)

    to_json(repo_path, outfile)
    # to_console(repo_path)
