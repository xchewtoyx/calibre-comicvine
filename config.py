'''
Configuration for the Comicvine metadata source
'''
from PyQt4.Qt import QWidget, QHBoxLayout, QLabel, QLineEdit
from calibre.utils.config import JSONConfig

try:
  import pycomicvine #pylint: disable=F0401
except ImportError:
  from calibre_plugins.comicvine import pycomicvine_dist as pycomicvine

PREFS = JSONConfig('plugins/comicvine')
PREFS.defaults['api_key'] = ''
PREFS.defaults['worker_threads'] = 16

pycomicvine.api_key = PREFS['api_key']

class ConfigWidget(QWidget):
  'Configuration widget'
  def __init__(self):
    QWidget.__init__(self)
    self.layout = QHBoxLayout()
    self.setLayout(self.layout)

    self.key_label = QLabel('&api key:')
    self.layout.addWidget(self.key_label)

    self.key_msg = QLineEdit(self)
    self.key_msg.setText(PREFS['api_key'])
    self.layout.addWidget(self.key_msg)
    self.label.setBuddy(self.key_msg)

    self.threads_label = QLabel('&worker_threads:')
    self.layout.addWidget(self.threads_label)

    self.threads_msg = QLineEdit(self)
    self.threads_msg.setText(PREFS['worker_threads.'])
    self.layout.addWidget(self.threads_msg)
    self.label.setBuddy(self.key_msg)

  def save_settings(self):
    'Apply new settings value'
    PREFS['api_key'] = unicode(self.key_msg.text())
    PREFS['worker_threads'] = int(self.threads_msg.text())
    pycomicvine.api_key = PREFS['api_key']

