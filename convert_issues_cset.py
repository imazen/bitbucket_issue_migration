# -*- coding: utf-8 -*-

import json
import sys
import re
import bisect


class NodeToHash(object):
    def __init__(self, hg_logs, git_logs, bb_url, gh_url):
        self.bb_url = bb_url
        self.gh_url = gh_url
        self.hg_to_git = {}
        date_to_hg = {}

        for hg_log in hg_logs:
            node = hg_log['node'].strip()
            date_to_hg[hg_log['date'].strip()] = node
            self.hg_to_git[node] = None

        for git_log in git_logs:
            date = git_log['date'].strip()
            if date not in date_to_hg:
                # print('%r is not found in hg log' % git_log)
                continue
            self.hg_to_git[date_to_hg[date]] = git_log['node'].strip()

        self.sorted_nodes = sorted(self.hg_to_git)

    def find_hg_node(self, hg_node):
        idx = bisect.bisect_left(self.sorted_nodes, hg_node)
        if idx == len(self.sorted_nodes):
            return None
        full_node = self.sorted_nodes[idx]
        if full_node.startswith(hg_node):
            return self.hg_to_git[full_node]
        return None

    def hgnode_to_githash(self, hg_node):
        git_hash = self.find_hg_node(hg_node)
        if git_hash is None:
            print('%r is not found in hg log' % hg_node)
            return '?'

        return git_hash

    def update_all(self, content):
        content = self.update_cset_marker(content)
        content = self.update_bb_cset_link(content)
        content = self.update_bb_issue_link(content)
        content = self.update_bb_src_link(content)
        return content

    def update_cset_marker(self, content):
        r"""
        replace '<<cset 0f18c81b53fc>>' pattern in content.

        before: '<<cset 0f18c81b53fc>>'  (hg-node)
        after: '\<\<cset 20fa9c09b23e\>\>'  (git-hash)
        """
        hg_nodes = re.findall(r'<<cset ([^>]+)>>', content)
        for hg_node in hg_nodes:
            git_hash = self.hgnode_to_githash(hg_node)
            content = content.replace(r'<<cset %s>>' % hg_node,
                                      r'\<\<cset %s\>\>' % git_hash)
        return content


    def update_bb_cset_link(self, content):
        r"""
        before: bb_url + '/commits/e282b3a8ef4802da3a685f10b5e9a39633e2c23a'
        after: gh_url + '/commit/1d063726ee185dce974f919f2ae696bd1b6b826b'
        """
        # TODO: implement update_bb_cset_link
        return content

    def update_bb_src_link(self, content):
        r"""
        before: bb_url + '/src/e2a0e4fde89998ed46198291457d2a822bc60125/sphinx/builders/html.py?at=default#cl-321'
        after: gh_url + '/blob/master/sphinx/builders/html.py#L321'
        """
        # TODO: implement update_bb_src_link
        return content

    def update_bb_issue_link(self, content):
        r"""
        before: bb_url + '/issue/63/make-sphinx'
        after: gh_url + '/issues/7'
        """
        # TODO: implement update_bb_issue_link
        return content


def convert_issues_cset(infile, outfile, hglogfile, gitlogfile):
    with open(hglogfile) as f:
        hglogs = json.load(f)['messages']
    with open(gitlogfile) as f:
        gitlogs = json.load(f)['messages']
    with open(infile) as f:
        issues = json.load(f)

    n2h = NodeToHash(
        hglogs,
        gitlogs,
        'https://bitbucket.org/birkenfeld/sphinx',
        'https://github.com/sphinx-doc/testing'
    )

    for issue in issues['issues']:
        issue['issue']['content'] = n2h.update_all(issue['issue']['content'])
        for comment in issue['comments']:
            comment['body'] = n2h.update_all(comment['body'])

    with open(outfile, 'w') as f:
        json.dump(issues, f, indent=4)


if __name__ == '__main__':
    try:
        infile, outfile, hglogfile, gitlogfile = sys.argv[1:5]
    except (ValueError, IndexError):
        print(
        'Usage:\n  {} input.json output.json hglog.json gitlog.json'.format(sys.argv[0]))
        sys.exit(-1)

    convert_issues_cset(infile, outfile, hglogfile, gitlogfile)
