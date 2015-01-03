#!/usr/bin/env python
# -*- coding: utf-8 -*-

# This file is part of the bitbucket issue migration script.
#
# The script is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# The script is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with the bitbucket issue migration script.
# If not, see <http://www.gnu.org/licenses/>.

import argparse
import urllib2
import getpass
import logging
import sys
import os
import time

import github
from github import Github, GithubException


logging.basicConfig(level=logging.ERROR)

try:
    import json
except ImportError:
    import simplejson as json


def output(string):
    sys.stdout.write(string)
    sys.stdout.flush()


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


def read_arguments():
    parser = argparse.ArgumentParser(
        description=(
            "A tool to migrate issues from Bitbucket to GitHub.\n"
            "note: the Bitbucket repository and issue tracker have to be"
            "public"
        )
    )

    parser.add_argument(
        "-u", "--bitbucket_username", dest="bb_user",
        help="Your Bitbucket username"
    )

    parser.add_argument(
        "-s", "--bitbucket_repo", dest="bb_repo",
        help="Bitbucket repository to pull data from."
    )

    parser.add_argument(
        "-g", "--github-username", dest="github_user",
        help="Your GitHub username"
    )

    parser.add_argument(
        "-d", "--github_repo", dest="github_repo",
        help="GitHub to add issues to. Format: <username>/<repo name>"
    )

    parser.add_argument(
        "-k", "--github_token", dest="github_token",
        help="The GitHub token to be used for authentication when adding issues to an organization")

    parser.add_argument(
        "-n", "--dry-run",
        action="store_true", dest="dry_run", default=False,
        help="Preform a dry run and print eveything."
    )

    parser.add_argument(
        "-v", "--verebose",
        action="store_true", dest="verbose", default=False,
        help="verbose printing."
    )

    parser.add_argument(
        "-f", "--start", type=int, dest="start", default=0,
        help="Bitbucket issue id from which to start import"
    )

    parser.add_argument(
        "-i", "--input", type=file, dest="infile", default=None,
        help="Input issues filename to post to Bitbucket"
    )

    parser.add_argument(
        "-o", "--output", type=argparse.FileType('w'), dest="outfile", default=None,
        help="Output filename to file with json format"
    )

    parser.add_argument(
        "-c", "--cache-dir", dest="cache_dir", default='.cache',
        help="cache directory. default=.cache"
    )

    parser.add_argument(
        "-m", "--meta_trans", dest="json_trans", default="meta_trans.json",
        help="JSON with BitBucket metadata to GitHub labels translation"
    )

    return parser.parse_args()


# Formatters
def format_user(author_info):
    if not author_info:
        return "Anonymous"

    if author_info['first_name'] and author_info['last_name']:
        return " ".join([author_info['first_name'], author_info['last_name']])

    if 'username' in author_info:
        return '[{0}](https://bitbucket.org/{0})'.format(
            author_info['username']
        )


def format_name(issue):
    if 'reported_by' in issue:
        return format_user(issue['reported_by'])
    else:
        return "Anonymous"


def format_body(bb_user, bb_repo, issue):
    content = clean_body(issue.get('content'))
    return u"""{}

{}
- Bitbucket: https://bitbucket.org/{}/{}/issue/{}
- Originally reported by: {}
- Originally created at: {}
""".format(
        content,
        '-' * 40,
        bb_user, bb_repo, issue['local_id'],
        format_name(issue),
        issue['created_on']
    )


def format_comment(comment):
    return u"""{}

{}
Original comment by: {}
""".format(
        comment['body'],
        '-' * 40,
        comment['user'].encode('utf-8')
    )


def clean_body(body):
    lines = []
    in_block = False
    for line in unicode(body).splitlines():
        if line.startswith("{{{") or line.startswith("}}}"):
            if "{{{" in line:
                before, part, after = line.partition("{{{")
                lines.append('    ' + after)
                in_block = True

            if "}}}" in line:
                before, part, after = line.partition("}}}")
                lines.append('    ' + before)
                in_block = False
        else:
            if in_block:
                lines.append("    " + line)
            else:
                lines.append(line.replace("{{{", "`").replace("}}}", "`"))
    content = "\n".join(lines)
    content = content.replace('%', '&#37;')
    return content


# Bitbucket fetch
def get_issues(bb_url, start_id):
    """
    Fetch the issues from Bitbucket
    """
    output('fetching issues: ')
    issues = []

    while True:
        url = "{}/?start={}".format(
            bb_url,
            start_id
        )

        try:
            response = urllib2.urlopen(url)
        except urllib2.HTTPError as ex:
            ex.message = (
                'Problem trying to connect to bitbucket ({url}): {ex} '
                'Hint: the bitbucket repository name is case-sensitive.'
                .format(url=url, ex=ex)
            )
            raise
        else:
            result = json.loads(response.read())
            if not result['issues']:
                # Check to see if there is issues to process if not break out.
                break

            issues += result['issues']
            start_id += len(result['issues'])
            output('...%d' % len(issues))

    output('\n')
    return issues


def convert_bb_comment_for_gh(comment):
    comment = {
        'user': format_user(comment['author_info']),
        'created_at': comment['utc_created_on'],
        'body': comment['content'] or '',
        'number': comment['comment_id']
    }
    return comment


def get_comments(bb_url, issue_id):
    """
    Fetch the comments for a Bitbucket issue
    """
    url = "{}/{}/comments/".format(
        bb_url,
        issue_id
    )
    result = json.loads(urllib2.urlopen(url).read())
    comments = sorted(result, key=lambda comment: comment["utc_created_on"])
    return comments


def prepare_milestones(gh_repo, use_milestone=None):
    created_milestones = []

    # Always re-read milestones and labels since we continously create them
    gh_milestones = {m.title: m.number for m in gh_repo.get_milestones()}

    # Should we create this milestone?
    milestone_tobe_create = None
    if use_milestone and use_milestone not in gh_milestones:
        milestone_tobe_create = use_milestone
        created_milestones += [milestone_tobe_create]

    return gh_milestones, created_milestones, milestone_tobe_create


def prepare_labels(gh_repo, issue, meta_trans):
    if 'metadata' not in issue:
        return [], []
    bb_meta = issue['metadata']

    # Always re-read milestones and labels since we continously create them
    gh_labels = [l.name for l in gh_repo.get_labels()]

    # What labels will be used for this issue?
    used_labels = []
    if bb_meta['component']:
        if bb_meta['component'] in meta_trans['comp']:
            used_labels.extend(meta_trans['comp'][bb_meta['component']])
        else:
            # If no translation is found for the component the label will have
            # the same component name
            used_labels.append(bb_meta['component'])

    if bb_meta['kind']:
        used_labels += meta_trans['kind'][bb_meta['kind']]
    if issue.get('status'):
        used_labels += meta_trans['status'][issue['status']]
    if issue.get('priority'):
        used_labels += meta_trans['prio'][issue['priority']]

    labels_tobe_create = []
    for l in used_labels:
        if l not in gh_labels:
            labels_tobe_create += [l]

    return used_labels, labels_tobe_create


# Cache Github tags, to avoid unnecessary API requests
@memoize()
def github_label(github_repo, name, color="FFFFFF"):
    """ Returns the Github label with the given name, creating it if necessary. """
    try:
        label = github_repo.get_label(name)
    except GithubException:
        label = github_repo.create_label(name, color)
    return label


def wait_and_retry(func, *args, **kwargs):
    while 1:
        try:
            return func(*args, **kwargs)
        except github.GithubException:
            output('w')
            time.sleep(60)


def add_comments_to_issue(github_issue, bb_comments, dry_run=False, verbose=False):
    """ Migrates all comments from a Bitbucket issue to its Github copy. """

    # Retrieve existing Github comments, to figure out which Google Code comments are new
    if not dry_run:
        existing_comments = [comment.body for comment in github_issue.get_comments()]
    else:
        existing_comments = []

    if len(bb_comments) > 0:
        output(", adding comments")

    for i, comment in enumerate(bb_comments):
        body = u'_From {user} on {created_at}_\n\n{body}'.format(**comment)
        if body in existing_comments:
            logging.info('Skipping comment %d: already present', i + 1)
        else:
            logging.info('Adding comment %d', i + 1)
            if not dry_run:
                wait_and_retry(github_issue.create_comment, body.encode('utf-8'))
                output('.')
            if verbose:
                output(body)
                output('\n')
    output('\n')


# GitHub push
def push_issue(github_repo, issue, meta_trans, dry_run=False, verbose=False):
    """ Migrates the given Bitbucket issue to Github. """

    output('Adding issue [%d]: %s' % (issue['local_id'], issue['title']))

    github_issue = None
    github_labels, labels_tobe_create = prepare_labels(github_repo, issue, meta_trans)

    bb_meta = issue.get('metadata', {})
    used_milestone = bb_meta.get('milestone')
    _, created_milestones, milestone_tobe_create = prepare_milestones(github_repo, used_milestone)

    if not dry_run:
        # Set the status and labels
        github_labels = [github_label(github_repo, l) for l in github_labels]

        # Create a milestone
        if milestone_tobe_create:
            output("Creating new milestone: {0}\n".format(milestone_tobe_create))
            github_repo.create_milestone(milestone_tobe_create)
        gh_milestones, _, _ = prepare_milestones(github_repo)

        if used_milestone:
            milestone = github_repo.get_milestone(gh_milestones[used_milestone])
        else:
            milestone = github.GithubObject.NotSet

        github_issue = wait_and_retry(
            github_repo.create_issue,
            issue['title'],
            body=issue['formatted'].encode('utf-8'),
            milestone=milestone,
            labels=github_labels)

        # Set the status of the issue
        if issue.get('status') in ['resolved', 'duplicate', 'wontfix', 'invalid']:
            github_issue.edit(state='closed')

    if verbose:
        output(issue['formatted'])
        output(u"Issue will tagged with these labels: {0}\n".format(github_labels))
        output(u"Need to create the following labels: {0}\n".format(labels_tobe_create))
        output(u"Milestone: {0}\n".format(used_milestone))
        output('\n')

    # Milestones

    return github_issue


def prepare_github(github_user, github_repo, token=None):

    if token:
        output("Authenticating to GitHub using token\n")
        github = Github(token)
    else:
        output("Log into Gituhub as {0}\n".format(github_user))
        while True:
            github_password = getpass.getpass("Github password: ")
            try:
                Github(github_user, github_password).get_user().login
                break
            except Exception:
                output("Bad credentials, try again.\n")
        github = Github(github_user, github_password)

    github_user = github.get_user()

    # If the project name is specified as owner/project, assume that it's owned by either
    # a different user than the one we have credentials for, or an organization.

    if "/" in github_repo:
        gh_user, gh_repo = github_repo.split('/')
        try:
            github_owner = github.get_user(gh_user)
        except GithubException:
            try:
                github_owner = github.get_organization(gh_user)
            except GithubException:
                github_owner = github_user
    else:
        github_owner = github_user

    gh_repo_obj = github_owner.get_repo(gh_repo)
    return gh_repo_obj


class IssueCache(object):

    COMMENT_FILE_PREFIX = 'comment-'
    ISSUE_FILE_NAME = 'issue.json'

    def __init__(self, base_dir, issue_id):
        self.issue_id = issue_id
        self.base_dir = base_dir

    @property
    def base_path(self):
        if self.base_dir is None:
            return None
        path = os.path.join(self.base_dir, str(self.issue_id))
        return path

    def save(self, name, data):
        path = self.base_path
        if not os.path.exists(path):
            os.makedirs(path)
        with open(os.path.join(path, name), 'w') as f:
            json.dump(data, f, indent=4)

    def load(self, name):
        path = self.base_path
        if path is None:
            return None
        try:
            with open(os.path.join(path, name), 'r') as f:
                return json.load(f)
        except:
            return None

    def delete_comments(self):
        path = self.base_path
        files = [f for f in os.listdir(path) if f.startswith('comments-')]
        for f in files:
            os.remove(os.path.join(path, f))

    def changed(self, issue):
        if self.issue is None:
            return True
        fmt = '%Y-%m-%d %H:%M:%S+00:00'
        return (
            time.strptime(self.issue['utc_last_updated'], fmt) <
            time.strptime(issue['utc_last_updated'], fmt)
        )

    @property
    def issue(self):
        return self.load(self.ISSUE_FILE_NAME)

    @issue.setter
    def issue(self, value):
        self.save(self.ISSUE_FILE_NAME, value)

    @property
    def comments(self):
        path = self.base_path
        comments = [
            self.load(f)
            for f in os.listdir(path)
            if f.startswith(self.COMMENT_FILE_PREFIX)
        ]
        comments = sorted(comments, key=lambda c: c["created_at"])
        return comments

    @comments.setter
    def comments(self, comments):
        self.delete_comments()
        for comment in comments:
            self.save('{0}{1[comment_id]}.json'.format(self.COMMENT_FILE_PREFIX, comment),
                      comment)


def iter_issue_from_file(infile, start=0, cache_dir=None):
    if start > 0:
        start -= 1
    data = json.load(infile)
    for issue in data['issues'][start:]:
        # cache = IssueCache(cache_dir, issue['id'])
        # cache.issue = issue['issue']
        # cache.comments = issue['comments']
        yield issue


def iter_issue_from_bb(bb_url, start=0, cache_dir=None):
    issues = get_issues(bb_url, start)

    # Sort issues, to sync issue numbers on freshly created GitHub projects.
    # Note: not memory efficient, could use too much memory on large projects.
    for issue in sorted(issues, key=lambda issue: issue['local_id']):
        issue_id = issue['local_id']
        cache = IssueCache(cache_dir, issue_id)
        if cache.changed(issue):
            cache.issue = issue
            output('fetching comments of issue [%d] ' % issue_id)
            comments = get_comments(bb_url, issue_id)
            cache.comments = comments
            output('.' * len(comments) + '\n')
        else:
            output('comments of issue [%d] is not changed\n' % issue_id)
            comments = cache.comments

        comments = [convert_bb_comment_for_gh(c) for c in comments]

        # File attached comments have in bitbucket no body
        comments = [c for c in comments if c['body']]  # filter no body comment

        yield {'id': issue_id, 'issue': issue, 'comments': comments}


def push_issues_to_github(issue, github_repo, meta_trans, dry_run=False, verbose=False):
    github_issue = push_issue(github_repo, issue['issue'], meta_trans, dry_run, verbose)
    add_comments_to_issue(github_issue, issue['comments'], dry_run, verbose)


def write_issues_to_file(issues, outfile):
    issues = list(issues)
    json.dump({'issues': issues}, outfile, indent=4)
    return len(issues)


def main(options):
    bb_url = "https://bitbucket.org/api/1.0/repositories/{}/{}/issues".format(
        options.bb_user,
        options.bb_repo
    )

    # load meta trans
    try:
        meta_trans = json.load(open(options.json_trans))
    except Exception as e:
        print "Could not open file {0}: {1}".format(options.json_trans, str(e))
        sys.exit(1)

    # prepare github information
    if not options.dry_run:
        github_repo = prepare_github(
            options.github_user, options.github_repo, options.github_token)
    else:
        github_repo = None

    if options.infile:
        iter_issue = lambda: iter_issue_from_file(options.infile, options.start,
                                                  options.cache_dir)
    else:
        iter_issue = lambda: iter_issue_from_bb(bb_url, options.start, options.cache_dir)

    if options.outfile:
        issues_count = write_issues_to_file(iter_issue(), options.outfile)
        output("Created {} issues to: {}\n".format(issues_count, options.outfile.name))
    else:
        for i, issue in enumerate(iter_issue()):
            issue['issue']['formatted'] = format_body(
                options.bb_user, options.bb_repo, issue['issue'])
            push_issues_to_github(issue, github_repo, meta_trans, options.dry_run, options.verbose)
        output("Created {} issues\n".format(i + 1))


if __name__ == "__main__":
    main(read_arguments())
