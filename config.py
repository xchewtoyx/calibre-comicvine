'''
Configuration for the Comicvine metadata source
'''
from PyQt4.Qt import QWidget, QHBoxLayout, QLabel, QLineEdit
from calibre_plugins.comicvine import pycomicvine
from calibre.utils.config import JSONConfig

PREFS = JSONConfig('plugins/comicvine')
PREFS.defaults['api_key'] = ''

class ConfigWidget(QWidget):
  'Configuration widget'
  def __init__(self):
    QWidget.__init__(self)
    self.layout = QHBoxLayout()
    self.setLayout(self.layout)

    self.label = QLabel('&api key:')
    self.layout.addWidget(self.label)

    self.msg = QLineEdit(self)
    self.msg.setText(PREFS['api_key'])
    self.layout.addWidget(self.msg)
    self.label.setBuddy(self.msg)

  def save_settings(self):
    'Apply new settings value'
    PREFS['api_key'] = unicode(self.msg.text())
    pycomicvine.api_key = PREFS['api_key']

