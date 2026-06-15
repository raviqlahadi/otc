-- Option Tracing Chatbot Schema Migration
-- Version: 001

CREATE TABLE knowledge_components (
    id VARCHAR(50) PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    description TEXT,
    prerequisite_kc_id VARCHAR(50) REFERENCES knowledge_components(id),
    display_order INTEGER NOT NULL
);

CREATE TABLE misconceptions (
    id VARCHAR(50) PRIMARY KEY,
    kc_id VARCHAR(50) NOT NULL REFERENCES knowledge_components(id),
    name VARCHAR(200) NOT NULL,
    description TEXT NOT NULL,
    why_incorrect TEXT NOT NULL,
    correct_method TEXT NOT NULL
);

CREATE TABLE questions (
    id VARCHAR(50) PRIMARY KEY,
    kc_id VARCHAR(50) NOT NULL REFERENCES knowledge_components(id),
    question_text TEXT NOT NULL,
    correct_option CHAR(1) NOT NULL CHECK (correct_option IN ('A', 'B', 'C', 'D')),
    option_a TEXT NOT NULL,
    option_b TEXT NOT NULL,
    option_c TEXT NOT NULL,
    option_d TEXT NOT NULL,
    is_verification BOOLEAN DEFAULT FALSE,
    target_misconception_id VARCHAR(50) REFERENCES misconceptions(id)
);

CREATE TABLE distractor_mappings (
    question_id VARCHAR(50) NOT NULL REFERENCES questions(id),
    option_letter CHAR(1) NOT NULL CHECK (option_letter IN ('A', 'B', 'C', 'D')),
    misconception_id VARCHAR(50) NOT NULL REFERENCES misconceptions(id),
    PRIMARY KEY (question_id, option_letter)
);

CREATE TABLE students (
    id VARCHAR(50) PRIMARY KEY,
    phone_hash VARCHAR(64) NOT NULL UNIQUE,
    created_at TIMESTAMP DEFAULT NOW(),
    last_active_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE student_mastery (
    student_id VARCHAR(50) NOT NULL REFERENCES students(id),
    kc_id VARCHAR(50) NOT NULL REFERENCES knowledge_components(id),
    p_mastery FLOAT NOT NULL DEFAULT 0.0 CHECK (p_mastery BETWEEN 0.0 AND 1.0),
    p_transition FLOAT NOT NULL DEFAULT 0.0 CHECK (p_transition BETWEEN 0.0 AND 1.0),
    status VARCHAR(20) DEFAULT 'active' CHECK (status IN ('active', 'mastered', 'needs_review')),
    last_updated TIMESTAMP DEFAULT NOW(),
    PRIMARY KEY (student_id, kc_id)
);

CREATE TABLE student_misconception_probs (
    student_id VARCHAR(50) NOT NULL REFERENCES students(id),
    kc_id VARCHAR(50) NOT NULL REFERENCES knowledge_components(id),
    misconception_id VARCHAR(50) NOT NULL REFERENCES misconceptions(id),
    probability FLOAT NOT NULL DEFAULT 0.0 CHECK (probability BETWEEN 0.0 AND 1.0),
    occurrence_count INTEGER DEFAULT 0,
    last_updated TIMESTAMP DEFAULT NOW(),
    PRIMARY KEY (student_id, kc_id, misconception_id)
);

CREATE TABLE interactions (
    id SERIAL PRIMARY KEY,
    student_id VARCHAR(50) NOT NULL REFERENCES students(id),
    question_id VARCHAR(50) NOT NULL REFERENCES questions(id),
    session_id VARCHAR(50) NOT NULL,
    attempt_number INTEGER NOT NULL CHECK (attempt_number BETWEEN 1 AND 3),
    selected_option CHAR(1) NOT NULL CHECK (selected_option IN ('A', 'B', 'C', 'D')),
    is_correct BOOLEAN NOT NULL,
    misconception_id VARCHAR(50) REFERENCES misconceptions(id),
    timestamp TIMESTAMP DEFAULT NOW()
);

CREATE TABLE verification_results (
    id SERIAL PRIMARY KEY,
    student_id VARCHAR(50) NOT NULL REFERENCES students(id),
    kc_id VARCHAR(50) NOT NULL REFERENCES knowledge_components(id),
    verification_question_id VARCHAR(50) NOT NULL REFERENCES questions(id),
    selected_option CHAR(1) NOT NULL,
    is_correct BOOLEAN NOT NULL,
    misconception_id_targeted VARCHAR(50) REFERENCES misconceptions(id),
    timestamp TIMESTAMP DEFAULT NOW()
);

CREATE TABLE student_progress (
    student_id VARCHAR(50) NOT NULL REFERENCES students(id),
    current_kc_id VARCHAR(50) NOT NULL REFERENCES knowledge_components(id),
    completed_kc_ids TEXT[] DEFAULT '{}',
    last_session_id VARCHAR(50),
    updated_at TIMESTAMP DEFAULT NOW(),
    PRIMARY KEY (student_id)
);

-- Indexes
CREATE INDEX idx_interactions_student ON interactions(student_id, timestamp);
CREATE INDEX idx_interactions_session ON interactions(session_id);
CREATE INDEX idx_student_mastery_student ON student_mastery(student_id);
CREATE INDEX idx_questions_kc ON questions(kc_id);
CREATE INDEX idx_questions_verification ON questions(kc_id, is_verification, target_misconception_id);
