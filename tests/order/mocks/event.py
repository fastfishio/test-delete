import json

from jsql import sql

from liborder import ctx


# Ignore schedule_at
def mock_get_events(action_code, num_events=3):
    events = sql(ctx.conn, '''
        SELECT *
        FROM boilerplate_event
        WHERE action_code = :action_code
        AND is_processed = 0
        LIMIT :limit
    ''', action_code=action_code.name, limit=num_events).dicts()
    for event in events:
        event['data'] = json.loads(event['data'])
    return events
