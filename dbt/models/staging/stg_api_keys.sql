select api_key_id, department
from {{ source('raw', 'api_keys') }}
