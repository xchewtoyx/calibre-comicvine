from PyQt4.Qt import QWidget, QHBoxLayout, QLabel, QLineEdit
from calibre_plugins.comicvine import pycomicvine
from calibre.utils.config import JSONConfig

prefs = JSONConfig('plugins/comicvine')

prefs.defaults['api_key'] = ''

class ConfigWidget(QWidget):
  def __init__(self):
    QWidget.__init__(self)
    self.l = QHBoxLayout()
    self.setLayout(self.l)

    self.label = QLabel('&api key:')
    self.l.addWidget(self.label)

    self.msg = QLineEdit(self)
    self.msg.setText(prefs['api_key'])
    self.l.addWidget(self.msg)
    self.label.setBuddy(self.msg)

  def save_settings(self):
    prefs['api_key'] = unicode(self.msg.text())
    pycomicvine.api_key = prefs['api_key']

  def commit(self):
    prefs.commit()