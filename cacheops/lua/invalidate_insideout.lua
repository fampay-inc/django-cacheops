local prefix = KEYS[1]
local db_table = ARGV[1]
local obj = cmsgpack.unpack(ARGV[2])

local conj_cache_key = function(db_table, scheme, obj)
    local parts = {}
    for field in string.gmatch(scheme, "[^,]+") do
        -- All obj values are strings, we still use tostring() in case obj does not contain field
        table.insert(parts, field .. '=' .. tostring(obj[field]))
    end

    -- Use key tagging with {table} to ensure keys are in the same hash slot in Redis Cluster
    return prefix .. 'conj:{' .. db_table .. '}:' .. table.concat(parts, '&')
end

-- Drop conj keys
local conj_keys = {}
local schemes = redis.call('smembers', prefix .. 'schemes:{' .. db_table .. '}')
for _, scheme in ipairs(schemes) do
    redis.call('unlink', conj_cache_key(db_table, scheme, obj))
end
