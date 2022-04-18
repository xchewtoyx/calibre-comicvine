'''
calibre_plugins.comicvine - A calibre metadata source for comicvine
'''
from calibre_plugins.comicvine.source import Comicvine

if __name__ == '__main__':
  from calibre import prints
  from calibre.ebooks.metadata.sources.test import (test_identify_plugin,
                                                    title_test, authors_test,
                                                    series_test)
  test_identify_plugin(Comicvine.name, [
      (
        {
          'title': 'heavy metal magazine #202008: vol. 300: all star special',
          'authors': ['Various', 'Claudia Scarletgothica', 'Dave Sharpe', 'Glenn Fabry']
          },
        [
          title_test('heavy metal magazine #202008: vol. 300: all star special', 
                     exact=False),
          authors_test(['duke mighten', 'jackson butch guice', 'mœbius', 'paul fry', 
          'agustin alessio', 'dave sharpe', 'jim terry', 'richard corben', 'protobunker studio', 
          'bruce edwards', 'geoff boucher', 'frank forte', 'dylan sprouse', 'northworld', 
          'bryan alvarez', 'brennan wagner', 'mark bode', 'giuseppe cafaro', 'joshua sky', 
          'mark mccann', 'glenn fabry', 'matthew medney', 'vaughn bode', 'kent williams', 
          'jaime martinez', 'justin mohlman', 'patrick norbert', 'adam brown', 'kelley jones', 
          'al barrionuevo', 'brendan columbus', 'claudia scarletgothica', 'chris sotomayor', 
          'marshall dillon', 'dan berger', 'german ponce', 'candice han', 'diego yapur', 
          'justin jordan', 'albert patin de la fizeliere', 'r. g. llarena', 'stephanie phillips', 
          'tater 7', 'david erwin', 'george c. romero', 'blake northcott']),
         ]
      ), 
    ]
)
