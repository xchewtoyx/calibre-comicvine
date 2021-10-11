'''
Configuration for the Comicvine metadata source
'''
import time

from PyQt5.Qt import QWidget, QGridLayout, QLabel, QLineEdit
from calibre.utils.config import JSONConfig

from calibre_plugins.comicvine  import pycomicvine

PREFS = JSONConfig('plugins/comicvine')
PREFS.defaults['api_key'] = ''
PREFS.defaults['worker_threads'] = 16
PREFS.defaults['requests_rate'] = 1
PREFS.defaults['requests_burst'] = 10
PREFS.defaults['requests_tokens'] = 0
PREFS.defaults['requests_update'] = time.time()
PREFS.defaults['max_volumes'] = 20
pycomicvine.api_key = PREFS['api_key']

class ConfigWidget(QWidget):
  'Configuration widget'
  def __init__(self):
    QWidget.__init__(self)
    self.layout = QGridLayout()
    self.layout.setSpacing(10)
    self.setLayout(self.layout)

    self.key_label = QLabel('&api key:')
    self.key_msg = QLineEdit(self)
    self.key_msg.setText(PREFS['api_key'])
    self.layout.addWidget(self.key_label, 1, 0)
    self.layout.addWidget(self.key_msg, 1, 1, 1, 2)
    self.key_label.setBuddy(self.key_msg)

    self.threads_label = QLabel('&worker_threads:')
    self.threads_msg = QLineEdit(self)
    self.threads_msg.setText(str(PREFS['worker_threads']))
    self.layout.addWidget(self.threads_label, 2, 0)
    self.layout.addWidget(self.threads_msg, 2, 1)
    self.threads_label.setBuddy(self.threads_msg)

    self.rate_label = QLabel('API &Requests per second:')
    self.rate_msg = QLineEdit(self)
    self.rate_msg.setText(str(PREFS['requests_rate']))
    self.layout.addWidget(self.rate_label, 3, 0)
    self.layout.addWidget(self.rate_msg, 3, 1)
    self.rate_label.setBuddy(self.rate_msg)

    self.maxvol_label = QLabel('&Maximum # of volumes returned:')
    self.maxvol_msg = QLineEdit(self)
    self.maxvol_msg.setText(str(PREFS['max_volumes']))
    self.layout.addWidget(self.maxvol_label, 4, 0)
    self.layout.addWidget(self.maxvol_msg, 4, 1)
    self.maxvol_label.setBuddy(self.maxvol_msg)

  def save_settings(self):
    'Apply new settings value'
    PREFS['api_key'] = str(self.key_msg.text())
    PREFS['worker_threads'] = int(self.threads_msg.text())
    PREFS['requests_rate'] = int(self.rate_msg.text())
    PREFS['max_volumes'] = int(self.maxvol_msg.text())
    pycomicvine.api_key = PREFS['api_key']

