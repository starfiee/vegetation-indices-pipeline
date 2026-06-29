-- vegetation_pipeline schema
-- Run once to set up all tables in vegetation_pipeline database

-- ── NDVI ──────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS ndvi_pixels (
    id          BIGINT(20)   NOT NULL AUTO_INCREMENT,
    field_id    BIGINT(20)   NOT NULL,
    image_date  DATE         NOT NULL,
    pixel_row   INT(11)      NOT NULL,
    pixel_col   INT(11)      NOT NULL,
    latitude    DOUBLE       NOT NULL,
    longitude   DOUBLE       NOT NULL,
    ndvi_value  FLOAT        NOT NULL,
    cloud_prob  FLOAT        NULL,
    ndvi_class  VARCHAR(50)  NULL,
    created_at  DATETIME     DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY unique_pixel (field_id, image_date, pixel_row, pixel_col),
    INDEX idx_field_date (field_id, image_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS ndvi_results (
    id           INT(11)      NOT NULL AUTO_INCREMENT,
    field_id     BIGINT(20)   NOT NULL,
    image_date   DATE         NOT NULL,
    ndvi_min     FLOAT        NULL,
    ndvi_max     FLOAT        NULL,
    ndvi_mean    FLOAT        NULL,
    cloud_prob   FLOAT        NULL,
    total_pixels INT(11)      NULL,
    valid_pixels INT(11)      NULL,
    status       VARCHAR(20)  NULL,
    created_at   DATETIME     DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY unique_result (field_id, image_date),
    INDEX idx_field_date (field_id, image_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ── NDMI ──────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS ndmi_pixels (
    id          BIGINT(20)   NOT NULL AUTO_INCREMENT,
    field_id    BIGINT(20)   NOT NULL,
    image_date  DATE         NOT NULL,
    pixel_row   INT(11)      NOT NULL,
    pixel_col   INT(11)      NOT NULL,
    latitude    DOUBLE       NOT NULL,
    longitude   DOUBLE       NOT NULL,
    ndmi_value  FLOAT        NOT NULL,
    cloud_prob  FLOAT        NULL,
    ndmi_class  VARCHAR(50)  NULL,
    created_at  DATETIME     DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY unique_pixel (field_id, image_date, pixel_row, pixel_col),
    INDEX idx_field_date (field_id, image_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS ndmi_results (
    id           INT(11)      NOT NULL AUTO_INCREMENT,
    field_id     BIGINT(20)   NOT NULL,
    image_date   DATE         NOT NULL,
    ndmi_min     FLOAT        NULL,
    ndmi_max     FLOAT        NULL,
    ndmi_mean    FLOAT        NULL,
    cloud_prob   FLOAT        NULL,
    total_pixels INT(11)      NULL,
    valid_pixels INT(11)      NULL,
    status       VARCHAR(20)  NULL,
    created_at   DATETIME     DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY unique_result (field_id, image_date),
    INDEX idx_field_date (field_id, image_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ── NDRE ──────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS ndre_pixels (
    id          BIGINT(20)   NOT NULL AUTO_INCREMENT,
    field_id    BIGINT(20)   NOT NULL,
    image_date  DATE         NOT NULL,
    pixel_row   INT(11)      NOT NULL,
    pixel_col   INT(11)      NOT NULL,
    latitude    DOUBLE       NOT NULL,
    longitude   DOUBLE       NOT NULL,
    ndre_value  FLOAT        NOT NULL,
    cloud_prob  FLOAT        NULL,
    ndre_class  VARCHAR(50)  NULL,
    created_at  DATETIME     DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY unique_pixel (field_id, image_date, pixel_row, pixel_col),
    INDEX idx_field_date (field_id, image_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS ndre_results (
    id           INT(11)      NOT NULL AUTO_INCREMENT,
    field_id     BIGINT(20)   NOT NULL,
    image_date   DATE         NOT NULL,
    ndre_min     FLOAT        NULL,
    ndre_max     FLOAT        NULL,
    ndre_mean    FLOAT        NULL,
    cloud_prob   FLOAT        NULL,
    total_pixels INT(11)      NULL,
    valid_pixels INT(11)      NULL,
    status       VARCHAR(20)  NULL,
    created_at   DATETIME     DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY unique_result (field_id, image_date),
    INDEX idx_field_date (field_id, image_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;