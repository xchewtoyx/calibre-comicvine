from calibre.ebooks.metadata.book.base import Metadata
from calibre.ebooks.metadata.sources.base import Source
from calibre.utils import logging as calibre_logging
from calibre_plugins.comicvine import pycomicvine
from calibre_plugins.comicvine.config import prefs
import logging
import re

class CalibreHandler(logging.Handler):
  def emit(self, record):
    level = getattr(calibre_logging, record.levelname)
    calibre_logging.default_log.prints(level, record.getMessage())

class Comicvine(Source):
  name = 'Comicvine'
  description = 'Downloads metadata and covers from Comicvine'
  author = 'Russell Heilling'
  version = (0,1,0)
  capabilities = frozenset(['identify'])
  touched_fields = frozenset([
      'title', 'authors', 'identifier:comicvine', 'comments', 'publisher', 
      'pubdate', 'series'
      ]);
                               
  has_html_comments = True
  can_get_multiple_covers = True
  
  def config_widget(self):
    from calibre_plugins.comicvine.config import ConfigWidget
    return ConfigWidget()

  def save_settings(self, config_widget):
    config_widget.save_settings()

  def is_configured(self):
    self.logger = logging.getLogger('urls')
    self.logger.setLevel(logging.DEBUG)
    self.logger.addHandler(CalibreHandler(logging.DEBUG))
    pycomicvine.api_key = prefs['api_key']
    return bool(pycomicvine.api_key)

  def get_title_tokens(self, title, strip_joiners=False, strip_subtitle=False):
    if title:
      title_patterns = [
        (re.compile(pat, re.IGNORECASE), repl) for pat, repl in [
          # Remove parenthesised strings
          (r'(?i)\([^)]*\)', ''),
          (r'(?i)[_+]+', ' '),
          ]]

    for pat, repl in title_patterns:
      title = pat.sub(repl, title)

    tokens = title.split()
    for token in tokens:
      token = token.strip()
      if token:
        yield token

  def identify(self, log, result_queue, abort, 
               title=None, authors=None, identifiers={}, timeout=30):
    filter_terms = {}
    matches = []
    issue_number = None

    # Do a simple lookup if comicvine identifier present
    comicvine_id = identifiers.get('comicvine')
    if comicvine_id is not None:
      log.info('Looking up Issue(%d)', comicvine_id)
      matches.append = pycomicvine.Issue(comicvine_id)

    # Otherwise look for title match in volumes
    title_tokens = []
    for token in self.get_title_tokens(title, strip_joiners=False):
      if token.startswith('#'):
        token = token.strip('#:')
        if token.isdigit():
          issue_number = int(token)
          break # Stop processing at issue number
      else:
        title_tokens.append(token)
    volume_title = ' '.join(title_tokens)
    filter_string = 'name:%s' % (volume_title)
    log.info('Looking up volume: %s', volume_title)
    candidate_volumes = pycomicvine.Volumes(
      filter=filter_string, field_list=['id', 'name', 'count_of_issues'])
    log.info('found %d matches', len(candidate_volumes))

    # Look for author match in People
    candidate_authors = []
    author_name = ' '.join(self.get_author_tokens(authors))
    if author_name and author_name != 'Unknown':
      log.info("Searching for author: %s", author_name)
      candidate_authors = pycomicvine.People(
        filter='name:%s' % (author_name), 
        field_list=['id', 'name'])
      log.info("%d matches found", len(candidate_authors))

    # look for volume + issue_number + author match in issues
    for volume in candidate_volumes:
      issue_filter = ['volume:%d' % volume.id]
      log.info('checking candidate Volume(%s[%d])', volume.name, volume.id)
      if issue_number:
        if issue_number > volume.count_of_issues:
          log.info('Volume(%d) only has %d issues, looking for #%d', volume.id,
                   volume.count_of_issues, issue_number)
          continue
        issue_filter.append('issue_number:%d' % issue_number)
      filter_string = ','.join(issue_filter)
      log.info('Searching for Issues(%s)', filter_string)
      candidate_issues = pycomicvine.Issues(
        filter=filter_string, field_ids=['id', 'volume', 'issue_number'])
      log.info('%d matches found', len(candidate_issues))
      for issue in candidate_issues:
        if candidate_authors:
          for author in candidate_authors:
            if issue in author.issues:
              log.info('Adding Issue(%d) to queue', issue.id)
              result_queue.put(self.build_meta(issue.id))
              break
        else:
          result_queue.put(self.build_meta(issue.id))

    return None

  def build_meta(self, issue_id):
    issue = pycomicvine.Issue(issue_id, field_ids=[
        'id', 'volume', 'issue_number', 'person_credits', 'description', 
        'publisher', 'store_date', 'cover_date'])
    title = '%s #%d' %  (issue.volume.name, issue.issue_number)
    if issue.name: 
      title = title + ': %s' % (issue.name)
    authors = [p.name for p in issue.person_credits]
    mi = Metadata(title, authors)
    mi.series = issue.volume.name
    mi.series_index = str(issue.issue_number)
    mi.set_identifier('comicvine', str(issue.id))
    mi.comments = issue.description
    mi.has_cover = False
    mi.publisher = issue.volume.publisher.name
    mi.pubdate = issue.store_date or issue.cover_date
    return mi

  def download_cover(self, log, result_queue, abort,
                     title=None, authors=None, identifiers={},
                     timeout=30, get_best_cover=False):
    pass

# Use calibre-debug -e __init__.py to run tests
if __name__ == '__main__':
  from calibre.ebooks.metadata.sources.test import (test_identify_plugin,
                                                    title_test, authors_test,
                                                    series_test)
  pycomicvine.api_key = prefs['api_key']
  test_identify_plugin(Comicvine.name, [
      (
        {
          'title': 'Preacher Special: The Story of You-Know-Who',
          'authors': 'Garth Ennis' 
          },
        [
          title_test('Preacher Special: The Story of You-Know-Who', 
                     exact=False),
          authors_test(['Garth Ennis', 'Richard Case', 'Matt Hollingsworth',
                        'Clem Robins', 'Glenn Fabry', 'Julie Rottenberg']),
         ]
      ), 
    ])
