'''
calibre_plugins.comicvine - A calibre metadata source for comicvine
'''
import pycomicvine

from calibre_plugins.comicvine.source import Comicvine # pylint: disable=F0401

if __name__ == '__main__':
  from calibre_plugins.comicvine.config import prefs # pylint: disable=F0401
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
