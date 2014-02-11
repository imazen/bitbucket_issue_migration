# bitbucket Issues Migration

This is a small script that will migrate bitbucket issues to a github project.
It will use the bitbucket api to pull out the issues and comments.

It will import issues (and close them as needed) and their comments. Labels and
milestones are not supported at the moment.

## Before running

You will need to install the requirements first

    pip install -r requirements.pip

## Example
    
    python migrate.py -h
    Usage: migrate.py [options]
    
    Options:
      -h, --help            show this help message and exit
      -t, --dry-run         Preform a dry run and print eveything.
      -g GITHUB_USERNAME, --github-username=GITHUB_USERNAME
                            GitHub username
      -d GITHUB_REPO, --github_repo=GITHUB_REPO
                            GitHub to add issues to. Format: <username>/<repo
                            name>
      -s BITBUCKET_REPO, --bitbucket_repo=BITBUCKET_REPO
                            Bitbucket repo to pull data from.
      -u BITBUCKET_USERNAME, --bitbucket_username=BITBUCKET_USERNAME
                            Bitbucket username
      -f JSON_META_TRANS, --meta_trans
                            JSON with BitBucket metadata to GitHub labels translation. Defaults to meta_trans.json
      -k GITHUB_API_TOKEN, --github_token
                            GitHub API token used for authentication (useful if GITHUB_USERNAME is an organization)

    python migrate.py -g <githbu_user> -d <github_repo> -s <bitbucket_repo> -u <bitbucket_usename>

Note: If you need to migrate to a GitHub organizational repository set the GitHub username to the organization repo
and use the GITHUB_API_TOKEN for authentication.

Note: If there's no meta mapping for a component from BitBucket, then a label with the origional name will be used.

None: All issues that are not new or open on BitBucket will be closed on GitHub (i.e wontfix, duplicate, invalid, closed)
