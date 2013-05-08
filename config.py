from PyQt4.Qt import QWidget, QHBoxLayout, QLabel, QLineEdit
from calibre_plugins.comicvine import pycomicvine
from calibre.utils.config import JSONConfig

prefs = JSONConfig('plugins/comicvine')
prefs.defaults['api_key'] = ''

class ConfigWidget(QWidget):
  'Configuration widget'
  def __init__(self):
    QWidget.__init__(self)
    self.layout = QHBoxLayout()
    self.setLayout(self.layout)

    self.label = QLabel('&api key:')
    self.layout.addWidget(self.label)

    self.msg = QLineEdit(self)
    self.msg.setText(prefs['api_key'])
    self.layout.addWidget(self.msg)
    self.label.setBuddy(self.msg)

  def save_settings(self):
    'Apply new settings value'
    prefs['api_key'] = unicode(self.msg.text())
    pycomicvine.api_key = prefs['api_key']

  def commit(self):
    'write out updated json file'
    prefs.commit()
