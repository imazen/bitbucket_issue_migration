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

from pygithub3 import Github
from datetime import datetime, timedelta
import urllib2
import time
import getpass
import codecs

import sys

try:
    import json
except ImportError:
    import simplejson as json

from optparse import OptionParser
parser = OptionParser()

parser.add_option("-t", "--dry-run", action="store_true", dest="dry_run", default=False,
    help="Preform a dry run and print eveything.")

parser.add_option("-g", "--github-username", dest="github_username",
    help="GitHub username")

parser.add_option("-d", "--github_repo", dest="github_repo",
    help="GitHub to add issues to. Format: <username>/<repo name>")

parser.add_option("-s", "--bitbucket_repo", dest="bitbucket_repo",
    help="Bitbucket repo to pull data from.")

parser.add_option("-u", "--bitbucket_username", dest="bitbucket_username",
    help="Bitbucket username")

parser.add_option("-f", "--meta_trans", dest="json_trans", default="meta_trans.json",
    help="JSON with BitBucket metadata to GitHub labels translation")

(options, args) = parser.parse_args()

try:
    meta_trans = json.load(open(options.json_trans))
except Exception as e:
    print "Could not open file {0}: {1}".format(options.json_trans, str(e))
    sys.exit(1)

print "Log into Gituhub as {0}".format(options.github_username)
github_password = getpass.getpass()

# Login in to github and create object
github = Github(login=options.github_username, password=github_password)

# Formatters

def format_user(author_info):
    name = "Anonymous"
    if not author_info:
        return name
    if 'first_name' in author_info and 'last_name' in author_info:
        name = " ".join([ author_info['first_name'],author_info['last_name']])
    elif 'username' in author_info:
        name = author_info['username']
    if 'username' in author_info:
        return '[%s](http://bitbucket.org/%s)' % (name, author_info['username'])
    else:
        return name

def format_name(issue):
    if 'reported_by' in issue:
        return format_user(issue['reported_by'])
    else:
        return "Anonymous"

def format_body(issue):
    content = clean_body(issue.get('content'))
    url = "https://bitbucket.org/%s/%s/issue/%s" % (options.bitbucket_username, options.bitbucket_repo, issue['local_id'])
    return content + """\n
---------------------------------------
- Bitbucket: %s
- Originally Reported By: %s
- Originally Created At: %s
""" % (url, format_name(issue), issue['created_on'])

def format_comment(comment):
    return comment['body'] + """\n
---------------------------------------
Original Comment By: %s
    """ % (comment['user'].encode('utf-8'))

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
    return "\n".join(lines)

def get_comments(issue):
    '''
    Fetch the comments for an issue
    '''
    url = "https://api.bitbucket.org/1.0/repositories/%s/%s/issues/%s/comments/" % (options.bitbucket_username, options.bitbucket_repo, issue['local_id'])
    result = json.loads(urllib2.urlopen(url).read())

    comments = []
    for comment in result:
        body = comment['content'] or ''

        # Status comments (assigned, version, etc. changes) have in bitbucket no body
        if body:
            comments.append({
                'user': format_user(comment['author_info']),
                'created_at': comment['utc_created_on'],
                'body': body.encode('utf-8'),
                'number': comment['comment_id']
            })

    return comments


start = 0
issue_counts = 0
created_labels = []
created_milestones = []
issues = []
while True:
    url = "https://api.bitbucket.org/1.0/repositories/%s/%s/issues/?start=%d" % (options.bitbucket_username, options.bitbucket_repo, start)
    response = urllib2.urlopen(url)
    result = json.loads(response.read())
    if not result['issues']:
        # Check to see if there is issues to process if not break out.
        break

    for issue in result['issues']:
        issues.append(issue)
        start += 1


# Sort issues, to sync issue numbers on freshly created GitHub projects.
# Note: not memory efficient, could use too much memory on large projects.
for issue in sorted(issues, key=lambda issue: issue['local_id']):
    comments = get_comments(issue)
    
    bb_meta = issue.get('metadata')

    # Always re-read milestones and labels since we continously create them
    gh_ms = {m.title:m.number for m in github.issues.milestones.list(user=options.github_username,
                                                                      repo=options.github_repo).all()}
    gh_lb = [l.name for l in github.issues.labels.list(user=options.github_username,
                                                       repo=options.github_repo).all()]

    m_used = bb_meta['milestone']

    if m_used:
        m_used = m_used.encode('utf-8')

    # Should we create this milestone?
    m_create = None
    if m_used and (m_used not in gh_ms.keys()):
        m_create = bb_meta['milestone'].encode('utf-8')
        created_milestones = m_create

    # What labels will be used for this issue?
    l_used = []
    if bb_meta['component']:
        # If no translation is found for the component the label will have
        # the same component name
        try:
            comp = meta_trans['comp'][bb_meta['component']]
        except:
            comp = [bb_meta['component']]
        l_used += comp
    if bb_meta['kind']:
        l_used += meta_trans['kind'][bb_meta['kind']]
    if issue.get('status'):
        l_used += meta_trans['status'][issue.get('status')]
    if issue.get('priority'):
        l_used += meta_trans['prio'][issue.get('priority')]

    l_create = []
    for l in l_used:
        if l not in gh_lb:
            l_create += [l]
    created_labels += l_create

    if options.dry_run:
        print u"Title: {0}".format(issue.get('title'))
        print u"Body: {0}".format(format_body(issue))
        print u"Milestone: {0}".format(bb_meta['milestone'])
        print u"Kind: {0}".format(bb_meta['kind'])
        print u"Component: {0}".format(bb_meta['component'])
        print u"Status: {0}".format(issue.get('status'))
        print u"Priority: {0}".format(issue.get('priority'))
        print u"Comments", [comment['body'] for comment in comments]
        print u"Issue will tagged with these labels: {0}".format(l_used)
        print u"Need to create the following labels: {0}".format(l_create)
        print u"This should be: {0}".format("closed" if issue.get('status') in ['resolved', 'duplicate', 'wontfix', 'invalid'] else "open")

    else:
        # Create the isssue with labels and milestones

        if m_create:
            print "Creating new milestone: {0}".format(m_create)
            github.issues.milestones.create(data={'title':m_create},
                                            user=options.github_username,
                                            repo=options.github_repo)


        for l in l_create:
            print "Creating new label: {0}".format(l.encode('utf-8'))
            github.issues.labels.create(data={'name':l.encode('utf-8'), 'color':'C0C0C0'},
                                            user=options.github_username,
                                            repo=options.github_repo)

        issue_data = {'title': issue.get('title').encode('utf-8'),
                      'body': format_body(issue).encode('utf-8')}

        if len(l_used) > 0:
            issue_data['labels'] = [l.encode('utf-8') for l in l_used]

        # This should be milestone number, not name
        if m_used:
            issue_data['milestone'] = gh_ms[m_used]

        print "Creating issue with data: {0}".format(issue_data)
        ni = github.issues.create(issue_data,
                                  options.github_username,
                                  options.github_repo)
        
        # Set the status of the issue
        if issue.get('status') in ['resolved', 'duplicate', 'wontfix', 'invalid']:
            github.issues.update(ni.number,
                                 {'state': 'closed'},
                                 user=options.github_username,
                                 repo=options.github_repo)
        
        # Add the comments
        comment_count = 0
        for comment in comments:
            github.issues.comments.create(ni.number,
                                        format_comment(comment),
                                        options.github_username,
                                        options.github_repo)
            comment_count += 1

        print "Created: {0} with {1} comments".format(issue['title'], comment_count)
    issue_counts += 1
    
print "---------------------------------------"
print "Created {0} issues".format(issue_counts)
# Remove duplicates created in dry-run
print "Created {0} labels: {1}".format(len(set(created_labels)), list(set(created_labels)))
print "Created {0} milestones: {1}".format(len(set(created_milestones)), list(set(created_milestones)))

sys.exit()
