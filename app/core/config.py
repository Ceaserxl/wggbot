import os
import configparser

BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
INI_PATH = os.path.join(BASE, "settings.ini")

config = configparser.ConfigParser()
config.read(INI_PATH)

def cfg(section, key, fallback=None):
    return config.get(section, key, fallback=fallback)

def cfg_bool(section, key, fallback=False):
    return config.getboolean(section, key, fallback=fallback)

