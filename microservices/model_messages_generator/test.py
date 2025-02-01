import json
import redis

# Example data
points = [
  {"x": 73, "y": 131},
  {"x": 303, "y": 164},
  {"x": 318, "y": 341},
  {"x": 95, "y": 314}
]

r = redis.Redis(host='192.168.1.201', port=6379, db=0)

# Convert Python list of dicts to JSON string
points_json = json.dumps(points)

# Store into Redis with a key, e.g. "my_detection_polygon"
r.set("DETECTION_POLYGON", points_json)