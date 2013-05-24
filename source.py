'''
calibre_plugins.comicvine - A calibre metadata source for comicvine
'''
#pylint: disable-msg=R0913,R0904
from functools import partial
import logging
from Queue import Queue

from calibre import setup_cli_handlers
from calibre.ebooks.metadata.sources.base import Source
from calibre.utils.config import OptionParser
import calibre.utils.logging as calibre_logging 
from calibre_plugins.comicvine.config import PREFS
from calibre_plugins.comicvine import utils

class Comicvine(Source):
  ''' Metadata source implementation '''
  name = 'Comicvine'
  description = 'Downloads metadata and covers from Comicvine'
  author = 'Russell Heilling'
  version = (0, 8, 2)
  capabilities = frozenset(['identify', 'cover'])
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
    Source.__init__(self, *args, **kwargs)

  def config_widget(self):
    from calibre_plugins.comicvine.config import ConfigWidget
    return ConfigWidget()

  def save_settings(self, config_widget):
    config_widget.save_settings()

  def is_configured(self):
    return bool(PREFS.get('api_key'))

  def cli_main(self, args):
    'Perform comicvine lookups from the calibre-debug cli'
    def option_parser():
      'Parse command line options'
      parser = OptionParser(
        usage='Comicvine [t:title] [a:authors] [i:id]')
      parser.add_option('--verbose', '-v', default=False, 
                        action='store_true', dest='verbose')
      parser.add_option('--debug_api', default=False,
                        action='store_true', dest='debug_api')
      return parser

    opts, args = option_parser().parse_args(args)
    if opts.debug_api:
      calibre_logging.default_log = calibre_logging.Log(
        level=calibre_logging.DEBUG)
    if opts.verbose:
      level = 'DEBUG'
    else:
      level = 'INFO'
    setup_cli_handlers(logging.getLogger('comicvine'), 
                       getattr(logging, level))
    log = calibre_logging.ThreadSafeLog(level=getattr(calibre_logging, level))

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
    self.identify(
      log, result_queue, False, title=title, authors=authors, identifiers=ids)
    ranking = self.identify_results_keygen(title, authors, ids)
    for result in sorted(result_queue.queue, key=ranking):
      if result.pubdate:
        pubdate = str(result.pubdate.date())
      else:
        pubdate = 'Unknown'
      log.info('(%04d) - %s: %s [%s]' % (
          ranking(result), result.identifiers['comicvine'], 
          result.title, pubdate))

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

  def download_cover(self, log, result_queue, abort, 
                     title=None, authors=None, identifiers=None, 
                     timeout=30, get_best_cover=False):
    if identifiers and 'comicvine' in identifiers:
      for url in utils.cover_urls(identifiers['comicvine'], get_best_cover):
        browser = self.browser
        log('Downloading cover from:', url)
        try:
          cdata = browser.open_novisit(url, timeout=timeout).read()
          result_queue.put((self, cdata))
        except:
          log.exception('Failed to download cover from:', url)

