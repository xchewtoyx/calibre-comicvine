from calibre.ebooks.metadata.book.base import Metadata
from calibre.ebooks.metadata.sources.base import Source
from calibre_plugins.comicvine.config import ConfigWidget, prefs

import pycomicvine

class Comicvine(Source):
  name = 'Comicvine'
  description = 'Downloads metadata and covers from Comicvine'
  author = 'Russell Heilling'
  version = (0,0,1)
  capabilities = frozenset(['identify'])
  touched_fields = frozenset([
      'title', 'authors', 'identifier:comicvine', 'comments', 'publisher', 
      'pubdate', 'series'
      ]);
                               
  has_html_comments = True
  can_get_multiple_covers = True
  
  def config_widget(self):
    return ConfigWidget(self)

  def is_configured(self):
    return False

  def identify(self, log, result_queue, abort, 
               title=None, authors=None, identifiers={}, timeout=30):
    filter_terms = {}
    matches = []
    issue_number = None
    comicvineid = identifiers.get('comicvine')
    if comicvineid is not None:
      matches.append = pycomicvine.Issue(comicvineid)
    # Look for title match in volumes
    title_tokens = []
    for token in self.get_title_tokens(title):
      if token.isdigit():
        issue_number = token
      else:
        title_tokens.append(token)
    volume_title = ' '.join(title_tokens)
    candidate_volumes = pycomicvine.Volumes(filter='name:%s' % (volume_title))
    # Look for author match in People
    author_name = ' '.join(self.get_author_tokens(authors))
    candidate_authors = pycomicvine.People(filter='name:%s' % (author_name))
    # look for volume + issue_number + author match in issues
    for volume in candidate_volumes:
      issue_filter = ['volume:%d' % volume.id]
      if issue_number:
        issue_filter.append('issue_number:%d' % issue_number)
      if candidate_authors:
        issue_filter.append('person:%d' % candidate_authors[0].id)
      candidate_issues = pycomicvine.Issues(filter=','.join(issue_filter))
      for issue in candidate_issues:
        request_queue.put(self.build_meta(issue))
    return None

  def build_meta(self, issue):
    title = '%s #%d: %s' % (issue.volume.name, issue.issue_number, 
                            issue.name)
    authors = [p.name for p in issue.people]
    mi = Metadata(title, authors)
    mi.series = issue.volume.name
    mi.series_index = issue.issue_number
    mi.set_identifier('comicvine', issue.id)
    mi.comments = issue.description
    mi.has_cover = False
    mi.publisher = issue.volume.publisher.name
    mi.pubdate = issue.shelf_date
    return mi

  def download_cover(self, log, result_queue, abort,
                     title=None, authors=None, identifiers={},
                     timeout=30, get_best_cover=False):
    pass
