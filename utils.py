'''
calibre_plugins.comicvine - A calibre metadata source for comicvine
'''
import logging
import re

try:
  import pycomicvine #pylint: disable=F0401
except ImportError:
  from calibre_plugins.comicvine import pycomicvine_dist as pycomicvine

from calibre.ebooks.metadata.book.base import Metadata
from calibre.utils import logging as calibre_logging # pylint: disable=W0404

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

def build_meta(log, issue_id):
  '''Build metadata record based on comicvine issue_id'''
  issue = pycomicvine.Issue(issue_id, field_list=[
      'id', 'name', 'volume', 'issue_number', 'person_credits', 'description', 
      'store_date', 'cover_date'])
  if not issue or not issue.volume:
    log.warn('Unable to load Issue(%d)' % issue_id)
    return None
  title = '%s #%s' %  (issue.volume.name, issue.issue_number)
  if issue.name: 
    title = title + ': %s' % (issue.name)
  authors = [p.name for p in issue.person_credits]
  meta = Metadata(title, authors)
  meta.series = issue.volume.name
  meta.series_index = str(issue.issue_number)
  meta.set_identifier('comicvine', str(issue.id))
  meta.set_identifier('comicvine-volume', str(issue.volume.id))
  meta.comments = issue.description
  meta.has_cover = False
  if issue.volume.publisher:
    meta.publisher = issue.volume.publisher.name
  meta.pubdate = issue.store_date or issue.cover_date
  return meta

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
    for i in range(len(matches)):
      try:
        if matches[i]:
          candidate_volumes.append(matches[i])
      except IndexError:
        continue 
  log.debug('found %d volume matches' % len(candidate_volumes))
  return candidate_volumes

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
        'id', 'name', 'volume', 'issue_number', 'description', 
        'store_date', 'cover_date', 'image']))
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
    (u'(?:# ?)?0*([\d\xbd]+[^:\s]*):?[^\d]*$', '#\g<1>'),
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
  candidate_volumes = find_volumes(' '.join(title_tokens), log, volumeid)
  return (issue_number, candidate_volumes)

def find_authors(query, authors, log):
  '''Find people matching author string'''
  candidate_authors = []
  author_name = ' '.join(query.get_author_tokens(authors))
  if author_name and author_name != 'Unknown':
    log.debug("Searching for author: %s" % author_name)
    candidate_authors = pycomicvine.People(
      filter='name:%s' % (author_name), 
      field_list=['id', 'name'])
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
      similarity = Levenshtein.ratio(unicode(volume), unicode(title))
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

def cover_urls(comicvine_id, get_best_cover=False):
  'Retrieve cover urls for comic in quality order'
  issue = pycomicvine.Issue(int(comicvine_id), field_list=['image'])
  for url in ['super_url', 'medium_url', 'small_url']:
    if url in issue.image:
      yield issue.image[url]
      if get_best_cover:
        break
  
