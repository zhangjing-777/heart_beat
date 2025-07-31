
-- 创建heart_beat表
CREATE TABLE IF NOT EXISTS heart_beat (
    id SERIAL PRIMARY KEY,
    ip_address VARCHAR(45) NOT NULL,
    mac_address VARCHAR(17) NOT NULL UNIQUE,
    sn VARCHAR(100) NOT NULL,
    beat_time TIMESTAMP WITH TIME ZONE NOT NULL,
    create_time TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 为heart_beat表创建索引
CREATE INDEX idx_heart_beat_mac ON heart_beat(mac_address);
CREATE INDEX idx_heart_beat_time ON heart_beat(beat_time);