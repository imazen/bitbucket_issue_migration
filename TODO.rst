procedure
==========

1. dump issues to json file::

   $ migrate.py birkenfeld sphinx shimizukawa sphinx-doc/testing-bb-issues -o issues.json -n

2. clone hg repository as sphinx-hg and create hglog.json::

   $ hglog2json.py /path/to/sphinx-hg hglog.json

3. clone git repository as sphinx-git and create gitlog.json::

   $ gitlog2json.py /path/to/sphinx-git gitlog.json

4. convert BB links and changeset markers in the issues.json::

   $ convert_issues.py issues.json issues_git.json hglog.json gitlog.json

5. push issues to github::

   $ migrate.py birkenfeld sphinx shimizukawa sphinx-doc/testing-bb-issues -i issues_git.json

TODO
=======

* write documentation

