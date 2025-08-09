CREATE TABLE IF NOT EXISTS game_events (
                                           ts DateTime,
                                           event_type String,
                                           user_id Nullable(Int64),
                                           user_source Nullable(String),
                                           payload String
)
    ENGINE = MergeTree()
ORDER BY (ts);
