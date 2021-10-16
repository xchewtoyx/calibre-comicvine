'''
calibre_plugins.comicvine - A calibre metadata source for comicvine
'''
import logging
import random
import re
import time
import threading

from calibre.ebooks.metadata.book.base import Metadata
from calibre.utils import logging as calibre_logging # pylint: disable=W0404
from calibre.utils.config import JSONConfig
from calibre_plugins.comicvine import pycomicvine
from calibre_plugins.comicvine.config import PREFS
from .pycomicvine.error import RateLimitExceededError

# Optional Import for fuzzy title matching
try:
  import Levenshtein
except ImportError:
  pass

class CalibreHandler(logging.Handler):
  '''
  python logging handler that directs messages to the calibre logging
  interface
  '''
  def emit(self, record):
    level = getattr(calibre_logging, record.levelname)
    calibre_logging.default_log.prints(level, record.getMessage())

class TokenBucket(object):
  def __init__(self):
    self.lock = threading.RLock()
    params = JSONConfig('plugins/comicvine_tokens')
    params.defaults['tokens'] = 0
    params.defaults['update'] = time.time()
    self.params = params

  def consume(self):
    with self.lock:
      self.params.refresh()
      rate = PREFS['requests_rate']
      while self.tokens < 1:
        if self.params['update'] + 1/rate > time.time():
          next_token = self.params['update'] + 1/rate - time.time()
        else:
          next_token = 1/rate
        if rate != 1 :
          logging.warn(
            'Slow down cowboy: %0.2f seconds to next token', next_token)
        time.sleep(next_token)
      self.params['tokens'] -= 1

  @property
  def tokens(self):
    with self.lock:
      self.params.refresh()
      if self.params['tokens'] < PREFS['requests_burst']:
        now = time.time()
        elapsed = now - self.params['update']
        if elapsed > 0:
          new_tokens = int(elapsed * PREFS['requests_rate'])
          if new_tokens:
            if new_tokens + self.params['tokens'] < PREFS['requests_burst']:
              self.params['tokens'] += new_tokens
            else:
              self.params['tokens'] = PREFS['requests_burst']
            self.params['update'] = now
    return self.params['tokens']

def retry_on_cv_error(retries=2):
  '''Decorator for functions that access the comicvine api. 

  Retries the decorated function on error.'''
  def wrap_function(target_function):
    'Closure for the retry function giving access to decorator arguments.'
    def retry_function(*args, **kwargs):
      '''Decorate function to retry on error.

      The comicvine API can be a little flaky, so retry on error to make
      sure the error is real.

      If retries is exceeded will raise the original exception.
      '''
      for retry in range(1,retries+1):
        try:
          return target_function(*args, **kwargs)
        except RateLimitExceededError:
          logging.warn('API Rate limited exceeded.')
          raise
        except:
          logging.warn('Calling %r failed on attempt %d/%d with args: %r %r',
                       target_function, retry, retries, args, kwargs)
          if retry == retries:
            raise
          # Failures may be due to busy servers.  Be a good citizen and
          # back off for 100-600 ms before retrying.
          time.sleep(random.random()/2 + 0.1)
        else:
          break
    return retry_function
  return wrap_function

#@retry_on_cv_error()
def build_meta(log, issue):
  '''Build metadata record based on comicvine issue_id'''
  """ issue = pycomicvine.Issue(issue_id, field_list=[
      'id', 'name', 'volume', 'issue_number', 'person_credits', 'description', 
      'store_date', 'cover_date']) """
  if not issue or not issue.volume:
    log.warn('Unable to load Issue(%s)' % issue)
    return None
  title = '%s #%s' %  (issue.volume.name, issue.issue_number)
  if issue.name:
    title = title + ': %s' % (issue.name)
  log.debug('Looking up authors: %s' % issue.person_credits)
  authors = [p.name for p in issue.person_credits]
  meta = Metadata(title, authors)
  meta.series = issue.volume.name
  meta.series_index = str(issue.issue_number)
  meta.set_identifier('comicvine', str(issue.id))
  meta.set_identifier('comicvine-volume', str(issue.volume.id))
  meta.comments = issue.description
  if issue.image:
    meta.has_cover = True
  else:
    meta.has_cover = False
  if issue.volume.publisher:
    meta.publisher = issue.volume.publisher.name
  meta.pubdate = issue.store_date or issue.cover_date
  return meta

@retry_on_cv_error()
def find_volumes(volume_title, log, volumeid=None):
  '''Look up volumes matching title string'''
  candidate_volumes = []
  if volumeid:
    log.debug('Looking up volume: %d' % volumeid)
    candidate_volumes = [pycomicvine.Volume(volumeid)]
  else:
    log.debug('Looking up volume: %s' % volume_title)
    matches = pycomicvine.Volumes.search(
        query=volume_title, field_list=['id', 'name', 'count_of_issues', 
                                        'publisher'])
    max_matches = PREFS['max_volumes'] - 1
    for i in range(len(matches)):
      try:
        if matches[i]:
          candidate_volumes.append(matches[i])
          if (i >= max_matches):
            break
      except IndexError:
        continue 
  log.debug('found %d volume matches' % len(candidate_volumes))
  return candidate_volumes

@retry_on_cv_error()
def find_issues(candidate_volumes, issue_number, log):
  '''Find issues in candidate volumes matching issue_number'''
  candidate_issues = []
  issue_filter = ['volume:%s' % (
      '|'.join(str(volume.id) for volume in candidate_volumes))]
  if issue_number is not None:
    issue_filter.append('issue_number:%s' % issue_number)
  filter_string = ','.join(issue_filter)
  log.debug('Searching for Issues(%s)' % filter_string)
  candidate_issues = candidate_issues + list(
    pycomicvine.Issues(
      filter=filter_string, field_list=[
        'id', 'name', 'volume', 'issue_number', 'person_credits', 
        'description', 'store_date', 'cover_date', 'image']))
  log.debug('%d matches found' % len(candidate_issues))
  return candidate_issues

def normalised_title(query, title):
  '''
  returns (issue_number,title_tokens)
  
  This method takes the provided title and breaks it down into
  searchable components.  The issue number should be preceeded by a
  '#' mark or it will be treated as a word in the title.  Anything
  provided after the issue number (e.g. a sub-title) will be
  ignored.
  '''
  title_tokens = []
  issue_number = None
  replacements = (
    (r'((?:^|\s)(?:\w\.){2,})', lambda match: match.group(0).replace('.', '')),
    (r'\s\(?of \d+\)?', ''),
    (r'(?:v|vol)\s?\d+', ''),
    (r'\([^)]+\)', ''),
    ('(?:# ?)?0*([\d\xbd]+[^:\s]*):?[^\d]*$', '#\g<1>'),
    (r'\s{2,}', ' '),
  )
  for pattern, replacement in replacements:
    title = re.sub(pattern, replacement, title)
  issue_pattern = re.compile('#([^:\s]+)')
  issue_match = issue_pattern.search(title)
  if issue_match:
    issue_number = issue_match.group(1)
    title = issue_pattern.sub('', title)
  for token in query.get_title_tokens(title):
    title_tokens.append(token.lower())
  return issue_number, title_tokens

def find_title(query, title, log, volumeid=None):
  '''Extract volume name and issue number from issue title'''
  (issue_number, title_tokens) = normalised_title(query, title)
  log.debug("Searching for %s #%s" % (title_tokens, issue_number))
  if volumeid:
    volumeid = int(volumeid)
  '''
  - edit - issue number preceded by # returns empty search too often
  '''
  candidate_volumes = find_volumes(' AND '.join(title_tokens) + ' AND ' + str(issue_number), log, volumeid)
  return (issue_number, candidate_volumes)

def split_authors(query, authors):
  a_list=authors[0].split("&")
  return a_list

def build_term(type,parts):
    return ' '.join(x for x in parts)  

@retry_on_cv_error()
def find_authors(query, authors, log):
  '''Find people matching author string'''
  candidate_authors = []
  author_list = split_authors(query, authors)
  for author_name in author_list:
    q = ''
    name_tokens = None
    log.debug("Author %s" % author_name)
    a_tokens = query.get_author_tokens([author_name], only_first_author=False)
    if a_tokens:
      name_tokens = build_term('author', a_tokens)
    if name_tokens and name_tokens != 'Unknown':
      log.debug("Searching for author: %s" % name_tokens)
      aperson = pycomicvine.People(
        filter='name:%s' % (name_tokens), 
        field_list=['id'])
      if aperson:
        candidate_authors.append(pycomicvine.Person(
          aperson[0].id
        ))  
  log.debug("%d matches found" % len(candidate_authors))
  return candidate_authors

def score_title(metadata, title=None, issue_number=None, title_tokens=None):
  '''
  Calculate title matching ranking
  '''
  score = 0
  volume = '%s #%s' % (metadata.series.lower(), metadata.series_index)
  match_year = re.compile(r'\((\d{4})\)')
  year = match_year.search(title)
  if year:
    title = match_year.sub('', title)
    if metadata.pubdate:
      score += abs(metadata.pubdate.year - int(year.group(1)))
    else:
      score += 10 # penalise entries with no publication date
  score += abs(len(volume) - len(title))
  for token in title_tokens:
    if token not in volume:
      score += 10
    try:
      similarity = Levenshtein.ratio(str(volume), str(title))
      score += 100 - int(100 * similarity)
    except NameError:
      pass
  if issue_number is not None and metadata.series_index != issue_number:
    score += 50
  if metadata.series_index not in title:
    score += 10
  # De-preference TPBs by looking for the phrases "collecting issues", 
  # "containing issues", etc. in the comments
  # TODO(rgh): This should really be controlled by config
  collection = re.compile(r'(?:collect|contain)(?:s|ing) issues')
  if metadata.comments and collection.search(metadata.comments.lower()):
    score += 50

  return score

def keygen(metadata, title=None, authors=None, identifiers=None, **kwargs):
  '''
  Implement multi-result comparisons.
  
  1. Prefer an entry where the comicvine id matches
  2. Prefer similar titles using Levenshtein ratio (if module available)
  3. Penalise entries where the issue number is not in the title
  4. Prefer matching authors (the more matches, the higher the preference)
  '''
  score = 0
  if identifiers:
    try:
      if metadata.get_identifier('comicvine') == identifiers['comicvine']:
        return 0
    except (KeyError, AttributeError):
      pass
  if title:
    score += score_title(metadata, title=title, **kwargs)
  if authors:
    for author in authors:
      if author not in metadata.authors:
        score += 10
  return score

# Do not include the retry decorator for generator, as exceptions in
# generators are always fatal.  Functions that use this should be
# decorated instead.
def cover_urls(comicvine_id, get_best_cover=False):
  'Retrieve cover urls for comic in quality order'
  issue = pycomicvine.Issue(int(comicvine_id), field_list=['image'])
  for url in ['super_url', 'medium_url', 'small_url']:
    if url in issue.image:
      yield issue.image[url]
      if get_best_cover:
        break
  
