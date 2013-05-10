'''
calibre_plugins.comicvine - A calibre metadata source for comicvine
'''
#pylint: disable-msg=R0913,R0904
from functools import partial
import logging
from Queue import Queue

from calibre.ebooks.metadata.sources.base import Source
import calibre.utils.logging as calibre_logging 
from calibre_plugins.comicvine.config import PREFS
from calibre_plugins.comicvine import utils

import pycomicvine

class Comicvine(Source):
  ''' Metadata source implementation '''
  name = 'Comicvine'
  description = 'Downloads metadata and covers from Comicvine'
  author = 'Russell Heilling'
  version = (0, 6, 1)
  #TODO(xchewtoyx): Implement cover capability
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
    pycomicvine.api_key = PREFS['api_key']
    Source.__init__(self, *args, **kwargs)

  def config_widget(self):
    from calibre_plugins.comicvine.config import ConfigWidget
    return ConfigWidget()

  def save_settings(self, config_widget):
    config_widget.save_settings()

  def is_configured(self):
    return bool(pycomicvine.api_key)

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
    ranking = self.identify_results_keygen(title, authors, ids)
    for result in sorted(result_queue.queue, key=ranking):
      log.info('(%04d) - %s: %s [%s]' % (
          ranking(result), result.identifiers['comicvine'], 
          result.title, result.pubdate.date()))

  def enqueue(self, log, result_queue, issue_id):
    'Add a result entry to the result queue'
    log.debug('Adding Issue(%d) to queue' % issue_id)
    metadata = utils.build_meta(log, issue_id)
    if metadata:
      self.clean_downloaded_metadata(metadata)
      result_queue.put(metadata)
      log.debug('Added Issue(%s) to queue' % metadata.title)

  def identify_results_keygen(self, title=None, authors=None, 
                              identifiers=None):
    'Provide a keying function for result comparison'
    (issue_number, title_tokens) = utils.normalised_title(self, title)
    return partial(
      utils.keygen, title=title, authors=authors, identifiers=identifiers,
      issue_number=issue_number, title_tokens=title_tokens)

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
      (issue_number, candidate_volumes) = utils.find_title(self, title, log)

      # Look up candidate authors
      candidate_authors = utils.find_authors(self, authors, log)

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

