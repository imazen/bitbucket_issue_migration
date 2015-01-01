# -*- coding: utf-8 -*-
"""
Convert BB links and changeset markers in the issues.json

* Normalize BB old URLs.
* Convert BB changeset marker into GH.
* Convert BB changeset links into GH.
* Convert BB issue links into GH.
* Convert BB src links into GH.
* Insert dummy issue if the issue numbers are not consecutive.

run as::

   $ convert_issues.py issues.json issues_git.json hglog.json gitlog.json

"""
import json
import sys
import re
import bisect
import urlparse
import logging
import datetime
import urllib

import dateutil.parser


logging.basicConfig(
    format='%(levelname)s: %(message)s',
    level=logging.WARNING
)
logger = logging.getLogger(__name__)


class memoize(object):
    def __init__(self):
        self.cache = {}

    def make_key(self, *args, **kw):
        key = '-'.join(str(a) for a in args)
        key += '-'.join(str(k) + '=' + str(v) for k, v in kw.items())
        return key

    def __call__(self, func):
        def wrap(*args, **kw):
            key = self.make_key(*args, **kw)
            if key in self.cache:
                return self.cache[key]
            res = func(*args, **kw)
            self.cache[key] = res
            return res

        return wrap


@memoize()
def is_user_exist_in_bb(user):
    if user in ('name', 'names', 'class', 'import', 'property', 'ubuntu', 'wrap',
                'github', 'for', 'enumerate', 'item', 'itemize', 'type', 'title',
                'empty', 'replace', 'gmail', 'id', 'href', 'app', 'echo'):
        logging.info('user @%s is skipped. It\'s a some code.', user)
        return False
    base_user_api_url = 'https://bitbucket.org/api/1.0/users/'
    uo = urllib.urlopen(base_user_api_url + user)
    if uo.code == 200:
        logging.debug('user @%s is exist in BB.', user)
        return True
    else:
        logging.debug('user @%s is not found in BB.', user)
        return False


class BbToGh(object):
    def __init__(self, hg_logs, git_logs, bb_url, gh_url):
        self.bb_url = bb_url.rstrip('/')
        self.gh_url = gh_url.rstrip('/')
        self.hg_to_git = {}
        self.hg_dates = {}
        self.hg_revnum_to_hg_node = {}
        key_to_hg = {}

        for hg_log in hg_logs:
            node = hg_log['node'].strip()
            date = dateutil.parser.parse(hg_log['date'])
            self.hg_dates[node] = date
            key = (date, hg_log['desc'].strip())
            key_to_hg.setdefault(key, []).append(node)
            if len(key_to_hg[key]) > 1:
                logger.warning('duplicates "%s"\n %r', date, key_to_hg[key])
            self.hg_to_git[node] = None
            self.hg_revnum_to_hg_node[hg_log['revnum']] = node

        for git_log in git_logs:
            date = dateutil.parser.parse(git_log['date'])
            key = (date, git_log['desc'].strip())
            if key not in key_to_hg:
                logger.warning('"%s" is not found in hg log', date)
                continue
            for node in key_to_hg[key]:
                # override duplicates by newest git hash
                self.hg_to_git[node] = git_log['node'].strip()

        self.sorted_nodes = sorted(self.hg_to_git)

    def find_hg_node(self, hg_node):
        idx = bisect.bisect_left(self.sorted_nodes, hg_node)
        if idx == len(self.sorted_nodes):
            return None
        full_node = self.sorted_nodes[idx]
        if full_node.startswith(hg_node):
            return full_node
        return None

    def hgnode_to_githash(self, hg_node):
        if hg_node in ('tip',):
            return None
        full_node = self.find_hg_node(hg_node)
        if full_node is None:
            if hg_node.isdigit():
                hg_node = self.hg_revnum_to_hg_node[int(hg_node)]
                full_node = self.find_hg_node(hg_node)
                if full_node is None:
                    logger.warning('hg node %s is not found in hg log', hg_node)
                    return None
        git_hash = self.hg_to_git[full_node]
        if git_hash is None:
            logger.warning(
                'hg node %s "%s" is not found in git log',
                hg_node, self.hg_dates[full_node])
            return None

        return git_hash

    def convert_all(self, content):
        content = self.normalize_bb_url(content)
        content = self.convert_cset_marker(content)
        content = self.convert_bb_cset_link(content)
        content = self.convert_bb_issue_link(content)
        content = self.convert_bb_src_link(content)
        content = self.convert_bb_user_link(content)
        return content

    def convert_cset_marker(self, content):
        r"""
        before-1: '<<cset 0f18c81b53fc>>'  (hg-node)
        before-2: '<<changeset 0f18c81b53fc>>'  (hg-node)
        before-3: '<<changeset 123:0f18c81b53fc>>'  (hg-node)
        before-4: '<<changeset 123>>'  (hg-node)
        after: '\<\<cset 20fa9c09b23e\>\>'  (git-hash)
        """
        captures = re.findall(r'<<(cset|changeset) ([^>]+)>>', content)
        for marker, hg_node in captures:
            if ':' in hg_node:  # for '718:714c805d842f'
                git_hash = self.hgnode_to_githash(hg_node.split(':')[1])
            else:
                git_hash = self.hgnode_to_githash(hg_node)
            content = content.replace(r'<<%s %s>>' % (marker, hg_node),
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

    def convert_bb_user_link(self, content):
        r"""
        before: '@username'
        after: '[@username](https://bitbucket.org/username)'
        """
        #base_url = self.bb_url
        base_url = 'https://bitbucket.org/'
        pattern = r'(^|[^a-zA-Z0-9])@([a-zA-Z][a-zA-Z0-9_-]+)\b'
        for prefix, user in re.findall(pattern, content):
            if is_user_exist_in_bb(user):
                content = re.sub(pattern, r'\1[$\2](%s)' % (base_url + user), content)
        content = re.sub(r'\[\$([^]]+)\]', r'[@\1]', content)
        return content


def convert_issue_content(n2h, issue):
    issue['issue']['content'] = n2h.convert_all(issue['issue']['content'])
    for comment in issue['comments']:
        comment['body'] = n2h.convert_all(comment['body'])

def insert_missing_issue(issues):
    class RetryException(BaseException):
        pass

    while 1:
        try:
            for idx in range(len(issues)):
                if issues[idx]['id'] != idx + 1:
                    d = datetime.datetime.now()
                    issues.insert(idx, {
                        'id': idx + 1,
                        'issue': {
                            "status": "invalid",
                            "title": "(deleted)",
                            "created_on": d.isoformat(),
                            "content": "(deleted)\r\n",
                            "comment_count": 0,
                            "local_id": idx + 1,
                            "utc_created_on": d.isoformat(),
                        },
                        'comments': [],
                    })
        except RetryException:
            pass
        else:
            break


def main(infile, outfile, hglogfile, gitlogfile):
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
        convert_issue_content(n2h, issue)

    insert_missing_issue(issues['issues'])

    with open(outfile, 'w') as f:
        json.dump(issues, f, indent=4)


if __name__ == '__main__':
    try:
        infile, outfile, hglogfile, gitlogfile = sys.argv[1:5]
    except (ValueError, IndexError):
        print(
            'Usage:\n  {} input.json output.json hglog.json gitlog.json'.format(
                sys.argv[0]))
        sys.exit(-1)

    main(infile, outfile, hglogfile, gitlogfile)
