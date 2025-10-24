from collections import OrderedDict
import threading

lock = threading.Lock()
cache_content_size = 0
cache = OrderedDict()
max_object_size = 0
max_cache_size = 0

def init_cache(max_obj, max_cache):
    global max_object_size, max_cache_size
    max_object_size = max_obj
    max_cache_size = max_cache

# checks whether key exists in cache
def checkCache(key):
    return key in cache

# inserts a key into cache if it isn't already present within it
def insertIntoCache(key, response, body_size):
    global lock, cache_content_size, cache, max_object_size, max_cache_size
    if checkCache(key):
        return
    
    with lock:        
        if body_size > max_object_size:
            return
        
        while cache_content_size + body_size > max_cache_size:
            _, (_, old_body_size) = cache.popitem(last=False)
            cache_content_size -= old_body_size
        
        cache[key] = (response, body_size)
        cache_content_size += body_size

# returns value associated with given key, else None
def findInCache(key):
    global lock, cache
    if not checkCache(key):
        return None
    
    with lock:
        cache.move_to_end(key)
        return cache[key]