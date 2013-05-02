'''
calibre_plugins.comicvine - A calibre metadata source for comicvine
'''
import logging
import re

from calibre.ebooks.metadata.book.base import Metadata
from calibre.ebooks.metadata.sources.base import Source
from calibre.utils import logging as calibre_logging # pylint: disable=W0404
from calibre_plugins.comicvine import pycomicvine # pylint: disable=F0401
from calibre_plugins.comicvine.config import prefs # pylint: disable=F0401

class CalibreHandler(logging.Handler):
  '''
  python logging handler that directs messages to the calibre logging
  interface
  '''
  def emit(self, record):
    level = getattr(calibre_logging, record.levelname)
    calibre_logging.default_log.prints(level, record.getMessage())

class Comicvine(Source):
  ''' Metadata source implementation '''
  name = 'Comicvine'
  description = 'Downloads metadata and covers from Comicvine'
  author = 'Russell Heilling'
  version = (0, 2, 0)
  capabilities = frozenset(['identify'])
  touched_fields = frozenset([
      'title', 'authors', 'identifier:comicvine', 'comments', 'publisher', 
      'pubdate', 'series'
      ])
                               
  has_html_comments = True
  can_get_multiple_covers = True
  
  def __init__(self, *args, **kwargs):
    self.logger = logging.getLogger('urls')
    self.logger.setLevel(logging.DEBUG)
    self.logger.addHandler(CalibreHandler(logging.DEBUG))
    Source.__init__(self, *args, **kwargs)

  def config_widget(self):
    # pylint: disable=F0401
    from calibre_plugins.comicvine.config import ConfigWidget
    return ConfigWidget()

  def save_settings(self, config_widget):
    config_widget.save_settings()

  def is_configured(self):
    pycomicvine.api_key = prefs['api_key']
    return bool(pycomicvine.api_key)

  def get_title_tokens(self, title, strip_joiners=False, strip_subtitle=False):
    if title:
      title_patterns = [
        (re.compile(pat, re.IGNORECASE), repl) for pat, repl in [
          # Remove parenthesised strings
          (r'(?i)\([^)]*\)', ''),
          # Replace _ and + with spaces
          (r'(?i)[_+]+', ' '),
          ]]

    for pat, repl in title_patterns:
      title = pat.sub(repl, title)

    tokens = title.split()
    for token in tokens:
      token = token.strip()
      if token:
        yield token

  def _parse_title(self, title):
    '''Extract volume name and issue number from issue title'''
    title_tokens = []
    issue_number = None
    for token in self.get_title_tokens(title, strip_joiners=False):
      if token.startswith('#'):
        token = token.strip('#:')
        if token.isdigit():
          issue_number = int(token)
          break # Stop processing at issue number
      else:
        title_tokens.append(token)
    volume_title = ' '.join(title_tokens)
    return (volume_title, issue_number)

  def _find_authors(self, authors, log):
    '''Find people matching author string'''
    candidate_authors = []
    author_name = ' '.join(self.get_author_tokens(authors))
    if author_name and author_name != 'Unknown':
      log.info("Searching for author: %s", author_name)
      candidate_authors = pycomicvine.People(
        filter='name:%s' % (author_name), 
        field_list=['id', 'name'])
      log.info("%d matches found", len(candidate_authors))
    return candidate_authors


  def identify(self, log, result_queue, abort, 
               title=None, authors=None, identifiers=None, timeout=30):
    '''Attempt to identify comicvine Issue matching given parameters'''
    issue_number = None

    # Do a simple lookup if comicvine identifier present
    if identifiers:
      comicvine_id = identifiers.get('comicvine')
      if comicvine_id is not None:
        log.info('Looking up Issue(%d)' % comicvine_id)
        result_queue.put(pycomicvine.Issue(comicvine_id))

    # Look up candidate volumes based on title
    (volume_title, issue_number) = self._parse_title(title)
    candidate_volumes = find_volumes(volume_title, log)

    # Look up candidate authors
    candidate_authors = self._find_authors(authors, log)

    # Look up candidate issues
    candidate_issues = find_issues(candidate_volumes, issue_number, log)

    # Refine issue selection based on authors
    for issue in candidate_issues:
      if candidate_authors:
        for author in candidate_authors:
          if issue in author.issues:
            log.info('Adding Issue(%d) to queue', issue.id)
            result_queue.put(build_meta(issue.id))
            break
      else:
        result_queue.put(build_meta(issue.id))

    return None

def build_meta(issue_id):
  '''Build metadata record based on comicvine issue_id'''
  issue = pycomicvine.Issue(issue_id, field_ids=[
      'id', 'volume', 'issue_number', 'person_credits', 'description', 
      'publisher', 'store_date', 'cover_date'])
  title = '%s #%d' %  (issue.volume.name, issue.issue_number)
  if issue.name: 
    title = title + ': %s' % (issue.name)
  authors = [p.name for p in issue.person_credits]
  meta = Metadata(title, authors)
  meta.series = issue.volume.name
  meta.series_index = str(issue.issue_number)
  meta.set_identifier('comicvine', str(issue.id))
  meta.comments = issue.description
  meta.has_cover = False
  meta.publisher = issue.volume.publisher.name
  meta.pubdate = issue.store_date or issue.cover_date
  return meta


def find_volumes(volume_title, log):
  '''Look up volumes matching title string'''
  filter_string = 'name:%s' % (volume_title)
  log.info('Looking up volume: %s', volume_title)
  candidate_volumes = pycomicvine.Volumes(
    filter=filter_string, field_list=['id', 'name', 'count_of_issues'])
  log.info('found %d matches', len(candidate_volumes))
  return candidate_volumes

def find_issues(candidate_volumes, issue_number, log):
  '''Find issues in candidate volumes matching issue_number'''
  candidate_issues = []
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
    candidate_issues = candidate_issues + list(
      pycomicvine.Issues(
        filter=filter_string, field_ids=['id', 'volume', 'issue_number']))
    log.info('%d matches found', len(candidate_issues))
  return candidate_issues

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
    ]
)
