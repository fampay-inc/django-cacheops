import redis
import msgpack

# Sample Python dictionary
data = {"name": "Alice", "age": 30, "country": "Wonderland"}

# Serialize the dictionary using msgpack
packed_data = msgpack.packb(data)

# Connect to Redis
r = redis.Redis(host="localhost", port=6379, db=0)

# Lua script that unpacks msgpack and stores key-value pairs
lua_script = """
local msgpack = cmsgpack
local blob = ARGV[1]
local unpacked = msgpack.unpack(blob)

for k, v in pairs(unpacked) do
    redis.call('SET', k, v)
end
return true
"""

# Register the Lua script with Redis
script = r.register_script(lua_script)

# Call the Lua script with the packed data
script(args=[packed_data])

print("Data inserted into Redis as individual keys.")
