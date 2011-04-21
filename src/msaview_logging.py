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
argv_parsed = False
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

def parse_env(force=False, env_var=loglevel_env_var):
    """Parse loglevel settings from environment variables.
    
    This function will do nothing if argv_parsed is True, since argv 
    settings should take precedence, but this behaviour can be overridden 
    using force. argv_parsed is set for instance by parse_argv(). 
       
    """
    if argv_parsed and not force:
        return
    if env_var in os.environ:
        setLevels(os.environ[env_var])

def parse_argv(args=loglevel_args, argv=sys.argv):
    """Rudimentary command line argument parser.
    
    Only argv[1:3] are regarded. Any other occurences of args are 
    intentionally disregarded. This function is intentionally made as 
    simple as possible, to reduce the possibilities for the user to confuse
    itself.
     
    No attempt is made to provide useful feedback to the user, as this 
    should rather be don in the calling application but should 
    rather be done  this is rather left as an exercise for the 
    application programmer.
    
    Any calls to parse_env should precede calls to this function, as argv 
    settings should take precedence over environment variables. 
    
    """
    argv_parsed = True
    if len(argv) > 1 and argv[1] in args:
        setLevels(sys.argv[2])
    
def parse_loglevels():
    """Do the usual stuff with environment vars and command line args."""
    parse_env()
    parse_argv()
    
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
