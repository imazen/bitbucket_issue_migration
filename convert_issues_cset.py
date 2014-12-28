# -*- coding: utf-8 -*-

import json
import sys
import re
import bisect


class NodeToHash(object):
    def __init__(self, hg_logs, git_logs):
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

    def update_cset_marker(self, content):
        r"""
        replace '<<cset 0f18c81b53fc>>' pattern in content.

        before: '<<cset 0f18c81b53fc>>'  (hg-node)
        after: '\<\<cset 20fa9c09b23e\>\>'  (git-hash)
        """
        hg_nodes = re.findall(r'<<cset ([^>]+)>>', content)
        for hg_node in hg_nodes:
            git_hash = self.hgnode_to_githash(hg_node)
            content = content.replace(r'<<cset %s>>' % hg_node, r'\<\<cset %s\>\>' % git_hash)
        return content


def convert_issues_cset(infile, outfile, hglogfile, gitlogfile):
    with open(hglogfile) as f:
        hglogs = json.load(f)['messages']
    with open(gitlogfile) as f:
        gitlogs = json.load(f)['messages']
    with open(infile) as f:
        issues = json.load(f)

    n2h = NodeToHash(hglogs, gitlogs)

    for issue in issues['issues']:
        issue['issue']['content'] = n2h.update_cset_marker(issue['issue']['content'])
        for comment in issue['comments']:
            comment['body'] = n2h.update_cset_marker(comment['body'])

    with open(outfile, 'w') as f:
        json.dump(issues, f, indent=4)


if __name__ == '__main__':
    try:
        infile, outfile, hglogfile, gitlogfile = sys.argv[1:5]
    except (ValueError, IndexError):
        print('Usage:\n  {} input.json output.json hglog.json gitlog.json'.format(sys.argv[0]))
        sys.exit(-1)

    convert_issues_cset(infile, outfile, hglogfile, gitlogfile)
