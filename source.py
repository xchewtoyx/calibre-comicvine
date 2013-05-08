'''
calibre_plugins.comicvine - A calibre metadata source for comicvine
'''
import logging
import pycomicvine
import re

from Queue import Queue

from calibre.ebooks.metadata.sources.base import Source
import calibre.utils.logging as calibre_logging 
from calibre_plugins.comicvine.config import prefs
from calibre_plugins.comicvine import utils

class Comicvine(Source):
  ''' Metadata source implementation '''
  name = 'Comicvine'
  description = 'Downloads metadata and covers from Comicvine'
  author = 'Russell Heilling'
  version = (0, 5, 0)
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
    self.logger.addHandler(utils.CalibreHandler(logging.DEBUG))
    pycomicvine.api_key = prefs['api_key']
    Source.__init__(self, *args, **kwargs)

  def config_widget(self):
    # pylint: disable=F0401
    from calibre_plugins.comicvine.config import ConfigWidget
    return ConfigWidget()

  def save_settings(self, config_widget):
    config_widget.save_settings()

  def is_configured(self):
    return bool(pycomicvine.api_key)

  def _find_title(self, title, log):
    '''Extract volume name and issue number from issue title'''
    title_tokens = []
    issue_number = None
    volume = re.compile(r'^(?i)(v|vol)#?\d+$')
    for token in self.get_title_tokens(title):
      if volume.match(token):
        continue
      if token.startswith('#'):
        token = token.strip('#:')
        if token.isdigit():
          issue_number = int(token)
          break # Stop processing at issue number
      else:
        title_tokens.append(token)
    candidate_volumes = utils.find_volumes(' '.join(title_tokens), log)
    return (issue_number, candidate_volumes)

  def _find_authors(self, authors, log):
    '''Find people matching author string'''
    candidate_authors = []
    author_name = ' '.join(self.get_author_tokens(authors))
    if author_name and author_name != 'Unknown':
      log.debug("Searching for author: %s" % author_name)
      candidate_authors = pycomicvine.People(
        filter='name:%s' % (author_name), 
        field_list=['id', 'name'])
      log.debug("%d matches found" % len(candidate_authors))
    return candidate_authors

  def cli_main(self, args):
    (title, authors, ids) = (None, [], {})
    for arg in args:
      if arg.startswith('t:'):
        title = arg.split(':', 1)[1]
      if arg.startswith('a:'):
        authors.append(arg.split(':', 1)[1])
      if arg.startswith('i:'):
        (idtype, identifier) = arg.split(':', 2)[1:]
        ids[idtype] = int(identifier)
    result_queue = Queue()
    log = calibre_logging.default_log
    self.identify(
      log, result_queue, False, title=title, authors=authors, identifiers=ids)
    for result in result_queue.queue:
      log.info('Found: %s [%s]' % (result.title, result.pubdate))

  def enqueue(self, log, result_queue, issue_id):
    'Add a result entry to the result queue'
    log.debug('Adding Issue(%d) to queue' % issue_id)
    metadata = utils.build_meta(log, issue_id)
    if metadata:
      self.clean_downloaded_metadata(metadata)
      result_queue.put(metadata)
      log.debug('Added Issue(%s) to queue' % metadata.title)

  def identify(self, log, result_queue, abort, 
               title=None, authors=None, identifiers=None, timeout=30):
    '''Attempt to identify comicvine Issue matching given parameters'''

    # Do a simple lookup if comicvine identifier present
    if identifiers:
      comicvine_id = int(identifiers.get('comicvine'))
      if comicvine_id is not None:
        log.debug('Looking up Issue(%d)' % comicvine_id)
        self.enqueue(log, result_queue, comicvine_id)
        return None

    if title:
      # Look up candidate volumes based on title
      (issue_number, candidate_volumes) = self._find_title(title, log)

      # Look up candidate authors
      candidate_authors = self._find_authors(authors, log)

      # Look up candidate issues
      candidate_issues = utils.find_issues(
        candidate_volumes, issue_number, log)

      # Refine issue selection based on authors
      for issue in candidate_issues:
        if candidate_authors:
          for author in candidate_authors:
            if issue in author.issues:
              self.enqueue(log, result_queue, issue.id)
              break
        else:
          self.enqueue(log, result_queue, issue.id)

    return None

