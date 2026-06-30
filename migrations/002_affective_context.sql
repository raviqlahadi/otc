-- Affective Context Schema Migration
-- Version: 002

CREATE TABLE student_profile (
    id SERIAL PRIMARY KEY,
    student_id VARCHAR(50) NOT NULL UNIQUE REFERENCES students(id),
    age INTEGER CHECK (age BETWEEN 15 AND 65),
    program_studi TEXT,
    semester VARCHAR(10),
    gender VARCHAR(30),
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE affective_survey (
    id SERIAL PRIMARY KEY,
    student_id VARCHAR(50) NOT NULL UNIQUE REFERENCES students(id),
    amas_responses JSONB,
    interest_responses JSONB,
    ses_responses JSONB,
    amas_total INTEGER CHECK (amas_total BETWEEN 9 AND 45),
    interest_total INTEGER CHECK (interest_total BETWEEN 3 AND 15),
    anxiety_level VARCHAR(10) CHECK (anxiety_level IN ('low', 'medium', 'high')),
    interest_level VARCHAR(10) CHECK (interest_level IN ('low', 'medium', 'high')),
    is_complete BOOLEAN DEFAULT FALSE,
    completed_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE feedback_personalisation (
    id SERIAL PRIMARY KEY,
    student_id VARCHAR(50) NOT NULL REFERENCES students(id),
    kc_id VARCHAR(50) NOT NULL REFERENCES knowledge_components(id),
    anxiety_level VARCHAR(10),
    interest_level VARCHAR(10),
    opening_used TEXT,
    feedback_body TEXT,
    full_message TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_affective_survey_student ON affective_survey(student_id);
CREATE INDEX idx_feedback_personalisation_student ON feedback_personalisation(student_id, created_at);
