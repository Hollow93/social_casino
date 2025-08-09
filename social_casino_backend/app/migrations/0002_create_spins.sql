CREATE TABLE IF NOT EXISTS spins (
                                     user_id String,
                                     event_type String,
                                     amount Float64,
                                     multiplier Float64,
                                     timestamp DateTime
)
    ENGINE = MergeTree()
ORDER BY (timestamp);
