import gtk

class Coordinate(object):
    def __init__(self, position=None, sequence=None, x=None, y=None, total_width=None, total_height=None):
        self.position = position
        self.sequence = sequence
        self.x = x
        self.y = y
        self.total_width = total_width
        self.total_height = total_height

class Action(object):
    # action names are case insensitive and should be short descriptions separated by dashes, e.g: copy-fasta
    action_name = ''
    # path determines where the action will end up in a context menu. Should be human readable both before and after instantiataion.
    path = ['']
    # nick should be a nicely readable action name, or '' if ' '.join(action.name.split('-')) will do. 
    nick = ''
    # tooltip should be a short description of what the action does, suitable for display in a tooltip popup.
    tooltip = None
    
    def __init__(self, target, coord=None):
        self.target = target
        self.coord = coord
        self.params = {}
        
    def __eq__(self, other):
        return (other.action_name == self.action_name and
                other.target == self.target)
    
    @classmethod
    def applicable(cls, target=None, coord=None):
        if True:
            return cls(target, coord)
    
    def get_options(self):
        return []
    
    def set_options(self, options):
        self.params.update((o.propname, o.value) for o in options)
     
    def run(self):
        pass

actions = []

def register_action(action):
    name = action.action_name.lower()
    for i in range(len(actions)):
        if actions[i].action_name.lower() == name:
            actions[i] = action
            break
    else:
        actions.append(action)
    actions.sort(key=lambda a: a.action_name.lower())
    
def find_applicable_target(root, action, coord=None):
    if action.applicable(root, coord):
        return root
    for c in root.children:
        target = find_applicable_target(c, action, coord)
        if target is not None:
            return target

def get_applicable(component, coord=None):
    l = []
    for action in actions:
        a = action.applicable(component, coord)
        if isinstance(a, (list, tuple)):
            l.extend(a)
        elif a:
            l.append(a)
    return l

def match_names(query, subject):
    query_parts = query.lower().split('-')
    subject_parts = subject.split('-')
    for i in range(len(subject_parts)-len(query_parts) + 1):
        if False not in [subject_parts[i+j].startswith(query_parts[j]) for j in range(len(query_parts))]:
            return True
    return False

def get_best_matching_name(query, items, key=None):
    parts = query.lower().split('-')
    matching = None
    for item in items:
        if key:
            name = key(item)
        else:
            name = item
        if query == name:
            return item
        if matching is not None:
            continue
        p = name.split('-')
        for i in range(len(p)-len(parts) + 1):
            if False not in [p[i+j].startswith(parts[j]) for j in range(len(parts))]:
                matching = item
    return matching
    
def get_action(test):
    if not isinstance(test, str):
        for a in actions:
            if test(a):
                return a
        return None
    return get_best_matching_name(test, actions, lambda a: a.action_name)

def get_actions(test):
    if isinstance(test, str):
        name = test
        test = lambda a: match_names(name, a.action_name)
    results = []
    for a in actions:
        if test(a):
            results.append(a)
    return results

def run_action(component, test, coord=None, params=None, parse=False):
    """Convenience function for running actions.
    
    component: (ancestor to a) component to run the action on.
    test: a (partial) action name that will be used with get_best_matching_name() 
        to determine which action to run. Can also be a boolean function that will
        be called with one action at a time from the action list, and the first
        action that evaluates to True will be run.
    coord: a Coord() object (tells where in the view the action should be run).
    params: a dict with parameters and values. Keys get evaluated using 
        get_best_matching_name() against the action's option propnames. Any 
        underscores will get converted to '-' prior to this. Omitted params get 
        default values.
    parse: if true then all param values will be parses using the options' 
        .from_str() method.    
    """
    if params is None:
        params = {}
    for key, value in params.items():
        if '_' in key:
            params[key.replace('_', '-')] = params.pop(key) 
    if not (isinstance(test, type) and issubclass(test, Action)):
        test = get_action(test)
    component = find_applicable_target(component, test, coord)
    a = test.applicable(component, coord)
    options = a.get_options()
    for name, value in params.items():
        option = get_best_matching_name(name, options, key=lambda o: o.propname)
        if parse:
            option.from_str(value)
        else:
            option.value = value
    a.set_options(options)
    a.run()
    
# Helpers:

def copy_text_to_clipboard(text, selection=None):
    if selection is None:
        selection = ("CLIPBOARD", "PRIMARY")
    for clipboard_name in selection:
        clipboard = gtk.Clipboard(selection=clipboard_name)
        clipboard.set_text(text)
        clipboard.store()
        
class CopyText(object):
    def run(self):
        copy_text_to_clipboard(self.get_text())

class ExportText(object):
    def run(self):
        print self.get_text()

