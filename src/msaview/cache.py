class CacheItem(object):
    def __init__(self, key, value):
        self.key = key
        self.hash = hash(key)
        self.value = value
        
class Cache(object):
    size = 100
    def __init__(self):
        self.items = []

    def __contains__(self, key):
        try:
            self.index(key)
        except KeyError:
            return False
        return True
    
    def __delitem__(self, key):
        self.items.pop(self.index(key))

    def __getitem__(self, key):
        i = self.index(key)
        item = self.items.pop(i)
        self.items.insert(0, item) 
        return item.value
    
    def __len__(self):
        return len(self.items)
    
    def __setitem__(self, key, value):
        try:
            i = self.index(key)
        except KeyError:
            pass
        else:
            self.items.pop(i)
        self.items.insert(0, CacheItem(key, value)) 
        if len(self.items) > self.size:
            self.items.pop()

    def index(self, key):
        h = hash(key)
        for i, item in enumerate(self.items):
            if item.hash == h and item.key == key:
                return i
        raise KeyError(key)
        
    def flush(self):
        self.items = []
    
    def get(self, key, default=None):
        try:
            return self[key]
        except KeyError:
            return default
    
    def peek(self, key):
        i = self.index(key)
        return self.items[i].value
    