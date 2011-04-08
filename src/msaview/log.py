import functools
import logging
import os
import sys
import time

levels = {'debug': logging.DEBUG,
          'info': logging.INFO,
          'warning': logging.WARNING,
          'error': logging.ERROR,
          'critical': logging.CRITICAL}

loglevel_args = ('--loglevel', '-L')
loglevel_env_var = "MSAVIEW_LOGLEVEL"
logger_name = "msaview"

def get_logger(name):
    """Get logger for module (dotted name) prefixed with name of root."""
    if not name.startswith(logger_name):
        name = logger_name + '.' + name
    return logging.getLogger(name)

def get_module_logger(path):
    name = logger_name + '.module.' + os.path.splitext(os.path.basename(path))[0]
    return logging.getLogger(name)

def get_plugin_module_logger(path):
    name = logger_name + '.module.plugins.' + os.path.splitext(os.path.basename(path))[0]
    return logging.getLogger(name)

logger = logging.getLogger(logger_name)
handler = logging.StreamHandler()
handler.setLevel(logging.NOTSET)
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
handler.setFormatter(formatter)
logger.addHandler(handler)

def parseLevel(literal):
    if literal.isdigit():
        return int(literal)
    literal = literal.strip().lower()
    level = levels.get(literal, None)
    if level is not None:
        return level 
    for name, level in levels.items(): 
        if name.startswith(literal):
            return level
    raise ValueError('no such level (%r)' % literal)

def setLevel(level):
    logger.setLevel(level)

def setLevels(literal):
    for setting in literal.split(','):
        if not setting:
            continue
        words = setting.split('=')
        if len(words) == 1:
            words.insert(0, logger_name)
        name = words[0].strip().lower() or logger_name
        level = parseLevel(words[1])
        if name == logger_name:
            level = max(level, 1)
        get_logger(name).setLevel(level)
        #print "setting %s to loglevel %s" % (name.lower(), level)

if loglevel_env_var in os.environ:
    setLevels(os.environ[loglevel_env_var])
    
if len(sys.argv) > 1 and sys.argv[1] in loglevel_args:
    setLevels(sys.argv[2])
    
def trace(f):
    """Decorator logs method enter/exit (info/debug) with the class logger."""
    @functools.wraps(f)
    def logwrapper(*args, **kw):
        args[0].logger.info("Entering: %s", f.__name__)
        t = time.time()
        return_value = f(*args, **kw)
        args[0].logger.debug("Exiting: %s (%.3fs)", f.__name__, time.time() - t)
        return return_value
    return logwrapper

def format_level(name):
    return logging.getLevelName(logging.getLogger(name).getEffectiveLevel())
