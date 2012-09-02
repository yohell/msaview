import gtk

class MsaviewAdjustment(gtk.Adjustment):
    def __init__(self, base_size=None):
        gtk.Adjustment.__init__(self)
        self.base_size = base_size
        
    value = property(lambda self: self.get_value(), lambda self, v: self.set_value(v))

    def _bound_value(self, value):
        return max(0, min(value, self.upper - self.page_size))
    
    def set_value(self, value):
        gtk.Adjustment.set_value(self, self._bound_value(value))

class ZoomAdjustment(MsaviewAdjustment):
    def __init__(self, base_size=None, magnitude=0):
        super(ZoomAdjustment, self).__init__(base_size)
        self.magnitude = magnitude
        
    def scroll_step(self, steps, page=False):
        amount = steps * (self.page_increment if page else self.step_increment)
        value = self._bound_value(self.value + amount)
        if value != self.value:
            self.value = value
        
    def scroll_to_edge(self, end=False):
        self.value = self.upper - self.page_size if end else 0
        
    def set_page_size(self, page_size):
        self.page_size = page_size
        self.step_increment = page_size * 0.1
        self.page_increment = page_size * 0.9
        value = self._bound_value(self.value)
        if value != self.value:
            self.value = value
        else:
            self.emit('value-changed')
            
    def zoom_step(self, steps, focus=0.5):
        offset = focus * self.page_size
        old_upper = self.upper
        self.magnitude += steps
        self.upper = int(self.base_size * 1.1 ** self.magnitude)
        value = self._bound_value((self.value + offset) * self.upper / old_upper - offset)
        if value != self.value:
            self.value = value
        else:
            self.emit('value-changed')
        
    def zoom_to_size(self, size, offset=None):
        if offset is None:
            offset = 0.5 * self.page_size
        old_upper = self.upper
        self.magnitude = 0
        self.base_size = size
        self.upper = size
        if old_upper > 0:
            value = self._bound_value((self.value + offset) * size / old_upper - offset)
        else:
            value = 0
        if value != self.value:
            self.value = value
        else:
            self.emit('value-changed')
        
    def zoom_to_fit(self, page_size):
        self.upper = page_size
        self.base_size = page_size
        self.magnitude = 0
        self.set_page_size(page_size)
        
