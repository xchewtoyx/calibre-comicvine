'''
calibre_plugins.comicvine - A calibre metadata source for comicvine
'''
import logging

import pycomicvine

from calibre.ebooks.metadata.book.base import Metadata
from calibre.utils import logging as calibre_logging # pylint: disable=W0404

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
  issue = pycomicvine.Issue(issue_id, field_ids=[
      'id', 'name', 'volume', 'issue_number', 'person_credits', 'description', 
      'publisher', 'store_date', 'cover_date'])
  if not issue:
    log.warn('Unable to load Issue(%d)' % issue_id)
    return None
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
  log.debug('Looking up volume: %s' % volume_title)
  candidate_volumes = pycomicvine.Volumes.search(
    query=volume_title, field_list=['id', 'name', 'count_of_issues'])
  log.debug('found %d matches' % len(candidate_volumes))
  return candidate_volumes

def find_issues(candidate_volumes, issue_number, log):
  '''Find issues in candidate volumes matching issue_number'''
  candidate_issues = []
  for volume in candidate_volumes:
    issue_filter = ['volume:%d' % volume.id]
    log.debug('checking candidate Volume(%s[%d])' % (volume.name, volume.id))
    if issue_number:
      issue_filter.append('issue_number:%d' % issue_number)
    filter_string = ','.join(issue_filter)
    log.debug('Searching for Issues(%s)' % filter_string)
    candidate_issues = candidate_issues + list(
      pycomicvine.Issues(
        filter=filter_string, field_ids=['id', 'volume', 'issue_number']))
    log.debug('%d matches found' % len(candidate_issues))
  return candidate_issues

