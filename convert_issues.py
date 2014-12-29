# -*- coding: utf-8 -*-
"""
Convert BB links and changeset markers in the issues.json

* Normalize BB old URLs.
* Convert BB changeset marker into GH.
* Convert BB changeset links into GH.
* Convert BB issue links into GH.
* Convert BB src links into GH.

run as::

   $ convert_issues.py issues.json issues_git.json hglog.json gitlog.json

"""
import json
import sys
import re
import bisect
import urlparse
import logging

logging.basicConfig(
    format='%(levelname)s: %(message)s',
    level=logging.DEBUG
)
logger = logging.getLogger(__name__)


class BbToGh(object):
    def __init__(self, hg_logs, git_logs, bb_url, gh_url):
        self.bb_url = bb_url.rstrip('/')
        self.gh_url = gh_url.rstrip('/')
        self.hg_to_git = {}
        date_to_hg = {}

        for hg_log in hg_logs:
            node = hg_log['node'].strip()
            date_to_hg[hg_log['date'].strip()] = node
            self.hg_to_git[node] = None

        for git_log in git_logs:
            date = git_log['date'].strip()
            if date not in date_to_hg:
                # logger.warning('%r is not found in hg log', git_log)
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
            logger.warning('%r is not found in hg log', hg_node)
            return None

        return git_hash

    def convert_all(self, content):
        content = self.normalize_bb_url(content)
        content = self.convert_cset_marker(content)
        content = self.convert_bb_cset_link(content)
        content = self.convert_bb_issue_link(content)
        content = self.convert_bb_src_link(content)
        return content

    def convert_cset_marker(self, content):
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

    def normalize_bb_url(self, content):
        content = content.replace('http://www.bitbucket.org/', 'https://bitbucket.org/')
        content = content.replace('http://bitbucket.org/', 'https://bitbucket.org/')
        content = content.replace('https://bitbucket.org/birkenfeld/sphinx/changeset/',
                                  'https://bitbucket.org/birkenfeld/sphinx/commits/')
        return content

    def convert_bb_cset_link(self, content):
        r"""
        before: bb_url + '/commits/e282b3a8ef4802da3a685f10b5e9a39633e2c23a'
        after: gh_url + '/commit/1d063726ee185dce974f919f2ae696bd1b6b826b'
        """
        base_url = self.bb_url + '/commits/'
        url_pairs = re.findall(base_url + r'([0-9a-f]+)(/?)', content)
        for hg_node, rest_of_url in url_pairs:
            git_hash = self.hgnode_to_githash(hg_node)
            from_ = base_url + hg_node + rest_of_url
            to_ = self.gh_url + '/commit/%s' % git_hash
            content = content.replace(from_, to_)
            logging.info("%s -> %s", from_, to_)
        return content

    def convert_bb_src_link(self, content):
        r"""
        before: bb_url + '/src/e2a0e4fde89998ed46198291457d2a822bc60125/sphinx/builders/html.py?at=default#cl-321'
        after: gh_url + '/blob/6336eab7c825852a058ed8a744be905c003ccbb8/sphinx/environment.py#L321'
        """
        base_url = self.bb_url + '/src/'
        url_pairs = re.findall(base_url + r'([^/]+)(/[\w\d/?=#.,_-]*)?', content)
        for hg_node, rest_of_url in url_pairs:
            parsed_url = urlparse.urlparse(rest_of_url)
            line = ''
            if re.match('cl-\d+', parsed_url.fragment):
                line = '#L' + re.match('cl-(\d+)', parsed_url.fragment).groups()[0]
            git_hash = self.hgnode_to_githash(hg_node)
            if git_hash is None:
                git_hash = 'master'
            from_ = base_url + hg_node + rest_of_url
            to_ = self.gh_url + '/blob/%s%s%s' % (git_hash, parsed_url.path, line)
            content = content.replace(from_, to_)
            logging.info("%s -> %s", from_, to_)
        return content

    def convert_bb_issue_link(self, content):
        r"""
        before: bb_url + '/issue/63/make-sphinx'
        after: gh_url + '/issues/7'
        """
        base_url = self.bb_url + '/issue/'
        issue_pairs = re.findall(base_url + r'(\d+)(/[\w\d.,_-]*)?', content)
        for issue_id, rest_of_url in issue_pairs:
            from_ = base_url + issue_id + rest_of_url
            to_ = self.gh_url + '/issues/%s' % issue_id
            content = content.replace(from_, to_)
            logging.info("%s -> %s", from_, to_)
        return content


def convert_issues(infile, outfile, hglogfile, gitlogfile):
    with open(hglogfile) as f:
        hglogs = json.load(f)['messages']
    with open(gitlogfile) as f:
        gitlogs = json.load(f)['messages']
    with open(infile) as f:
        issues = json.load(f)

    n2h = BbToGh(
        hglogs,
        gitlogs,
        'https://bitbucket.org/birkenfeld/sphinx',
        'https://github.com/sphinx-doc/testing'
    )

    for issue in issues['issues']:
        issue['issue']['content'] = n2h.convert_all(issue['issue']['content'])
        for comment in issue['comments']:
            comment['body'] = n2h.convert_all(comment['body'])

    with open(outfile, 'w') as f:
        json.dump(issues, f, indent=4)


if __name__ == '__main__':
    try:
        infile, outfile, hglogfile, gitlogfile = sys.argv[1:5]
    except (ValueError, IndexError):
        print(
        'Usage:\n  {} input.json output.json hglog.json gitlog.json'.format(sys.argv[0]))
        sys.exit(-1)

    convert_issues(infile, outfile, hglogfile, gitlogfile)
