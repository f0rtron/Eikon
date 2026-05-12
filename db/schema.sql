-- ============================================================
-- Smart Attendance System — Database Schema v2
-- Run: Get-Content db/schema.sql | mysql -u root -p
-- ============================================================

CREATE DATABASE IF NOT EXISTS smart_attendance
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;

USE smart_attendance;

-- ─── Users ───────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS users (
    id            INT          AUTO_INCREMENT PRIMARY KEY,
    username      VARCHAR(50)  NOT NULL UNIQUE,
    email         VARCHAR(100) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    role          ENUM('admin', 'teacher') NOT NULL DEFAULT 'teacher',
    is_active     BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_login    DATETIME     NULL
);

-- ─── Subjects ────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS subjects (
    id               INT          AUTO_INCREMENT PRIMARY KEY,
    name             VARCHAR(100) NOT NULL,
    code             VARCHAR(20)  NOT NULL UNIQUE,
    teacher_id       INT          NULL,
    class_start_time TIME         NULL,
    class_end_time   TIME         NULL,
    is_active        BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at       DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (teacher_id) REFERENCES users(id) ON DELETE SET NULL
);

-- ─── Students ─────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS students (
    id                  INT          AUTO_INCREMENT PRIMARY KEY,
    reg_number          VARCHAR(30)  NOT NULL UNIQUE,
    name                VARCHAR(100) NOT NULL,
    email               VARCHAR(100) NULL,
    class_name          VARCHAR(50)  NULL,
    dataset_path        VARCHAR(255) NULL,
    is_encoded          BOOLEAN      NOT NULL DEFAULT FALSE,
    needs_reregistration BOOLEAN     NOT NULL DEFAULT FALSE,
    is_active           BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at          DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ─── Attendance ───────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS attendance (
    id          INT      AUTO_INCREMENT PRIMARY KEY,
    student_id  INT      NOT NULL,
    subject_id  INT      NOT NULL,
    marked_at   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    marked_date DATE     NOT NULL,
    confidence  FLOAT    NOT NULL,
    status      ENUM('present', 'late', 'manual') NOT NULL DEFAULT 'present',
    photo_path  VARCHAR(255) NULL,
    UNIQUE KEY unique_daily (student_id, subject_id, marked_date),
    FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE,
    FOREIGN KEY (subject_id) REFERENCES subjects(id) ON DELETE CASCADE
);

CREATE INDEX idx_att_date    ON attendance(marked_date);
CREATE INDEX idx_att_student ON attendance(student_id);
CREATE INDEX idx_att_subject ON attendance(subject_id);

-- ─── Seed data ────────────────────────────────────────────────────────────────
INSERT IGNORE INTO users (username, email, password_hash, role) VALUES (
    'admin',
    'admin@smartattendance.local',
    '$2b$12$92IXUNpkjO0rOQ5byMi.Ye4oKoEa3Ro9llC/.og/at2uheWG/igi.',
    'admin'
);

INSERT IGNORE INTO subjects (name, code, class_start_time, class_end_time) VALUES
    ('Computer Science', 'CS-101',   '08:00:00', '09:30:00'),
    ('Mathematics',      'MATH-101', '10:00:00', '11:30:00'),
    ('Physics',          'PHY-101',  '13:00:00', '14:30:00');
